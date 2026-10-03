# MÓDULO DE INGESTA: scraping real + Dask (ejecución distribuida) + Prefect (orquestación y observabilidad).
#
#   Prefect = el "capataz": define el flujo, programa cada cuánto corre, reintenta lo que falla
#             y muestra todo en su panel (http://localhost:4200).
#   Dask    = la "cuadrilla": un scheduler que reparte las tareas entre varios workers
#             (contenedores dask-worker) que las ejecutan EN PARALELO (panel: http://localhost:8787).
#
# Fuente: Hostelworld (plataforma comercial real de reservas de hostales).
# Se eligió porque su robots.txt PERMITE las páginas de ciudad (/hostels/...) y no responde con desafíos anti-bot.
# (Booking.com se probó primero: responde con un desafío anti-bot de AWS WAF; evadirlo no es aceptable.)
#
# Scraping responsable:
#   - Se lee y respeta robots.txt antes de descargar.
#   - El User-Agent identifica honestamente al bot (no se disfraza de navegador).
#   - Una sola petición por ciudad en cada ejecución.
#   - Si el sitio responde con un desafío anti-bot, la tarea FALLA: no se intenta evadirlo.

import os
import random
import re
from datetime import timedelta
from decimal import Decimal

import httpx
import psycopg
from bs4 import BeautifulSoup     # parser de HTML
# Parser de robots.txt que cumple el estándar RFC 9309 (el que usa Scrapy).
# NO se usa urllib.robotparser (librería estándar) porque es antiguo: no entiende comodines (* y $)
# y convierte la regla "Disallow: /s?" en "Disallow: /s", bloqueando por error todas las rutas /st/...
from protego import Protego
from prefect import flow, task
from prefect_dask import DaskTaskRunner

UA = "WanderSync-academic-bot/0.1 (proyecto universitario)"
BASE = "https://www.hostelworld.com"

# Código de ciudad (el mismo que usan las tablas de vuelos y autos) -> nombre de la ciudad en la URL del sitio
CIUDADES = {"MDE": "medellin", "CTG": "cartagena", "SMR": "santa-marta"}

DB = os.environ["DATABASE_URL"]                                  # BD "hoteles"
DASK_SCHEDULER = os.environ["DASK_SCHEDULER"]                    # tcp://dask-scheduler:8786
# Demo de retries: probabilidad (0 a 1) de simular un fallo de red al descargar. 0 = desactivado.
PROB_FALLO = float(os.environ.get("PROB_FALLO_SCRAPER", "0"))


# ---------------------------------------------------------------- TAREAS
# @task convierte la función en una tarea de Prefect: queda registrada (estado, duración, logs)
# y, gracias al DaskTaskRunner del flow, se ejecuta en un worker de Dask y no en este contenedor.

# retries=3 + retry_delay_seconds: si falla, Prefect la reintenta 3 veces esperando 5s, 15s y 45s
# (backoff: cada espera es mayor, para no saturar un sitio que quizá está caído).
@task(retries=3, retry_delay_seconds=[5, 15, 45])
def descargar(codigo: str) -> str:
    """Paso 1 (scraping): descarga el HTML de la página de hostales de una ciudad."""
    url = f"{BASE}/hostels/south-america/colombia/{CIUDADES[codigo]}/"
    headers = {"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"}

    # 1. Respetar robots.txt: si el sitio no permite esa ruta a los bots, no se descarga.
    robots = httpx.get(f"{BASE}/robots.txt", headers=headers, timeout=15)
    reglas = Protego.parse(robots.text)
    if not reglas.can_fetch(url, UA):
        raise PermissionError(f"robots.txt no permite descargar {url}")

    # 2. Fallo simulado (solo si PROB_FALLO_SCRAPER > 0): para ver los retries en el panel de Prefect.
    if random.random() < PROB_FALLO:
        raise ConnectionError("Fallo de red simulado (demo de retries)")

    # 3. Descarga real
    r = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
    r.raise_for_status()   # 4xx/5xx -> excepción -> Prefect reintenta

    # 4. Si el sitio nos pone un desafío anti-bot, fallamos honestamente en vez de intentar evadirlo.
    if re.search(r"awswaf|captcha|cf-chl", r.text, re.I):
        raise RuntimeError("El sitio respondió con un desafío anti-bot; no se evade")
    return r.text


@task
def estructurar(html: str, codigo: str) -> list[dict]:
    """Paso 2 (estructuración): convierte el HTML en registros con los campos que nos interesan.
    Cada hostal aparece en una tarjeta <a class="property-card-container">."""
    soup = BeautifulSoup(html, "html.parser")
    hostales = {}
    for tarjeta in soup.select("a.property-card-container"):
        nombre = tarjeta.select_one(".property-name")
        # ".current.notranslate" (SIN espacio) = un elemento con AMBAS clases: class="current notranslate".
        # Con espacio (".current .notranslate") buscaría un .notranslate DENTRO de un .current y no encuentra nada.
        precio = tarjeta.select_one(".current.notranslate")    # ej: "CO$58349.63" (precio "desde", por noche)
        rating = tarjeta.select_one(".score")                  # ej: "9.7"
        if nombre is None or precio is None:
            continue   # tarjeta incompleta (ej: hostal sin disponibilidad)
        # Se indexa por URL: la misma propiedad puede aparecer 2 veces (destacada + listado) -> sin duplicados
        hostales[tarjeta["href"]] = {
            "url": tarjeta["href"],
            "ciudad": codigo,
            "nombre": nombre.get_text(strip=True),
            "precio": precio.get_text(strip=True),
            "rating": rating.get_text(strip=True) if rating else None,
        }
    return list(hostales.values())


@task
def limpiar(registros: list[dict]) -> list[dict]:
    """Paso 3 (limpieza): convierte textos a números y descarta datos inválidos."""
    limpios = []
    for r in registros:
        try:
            # "CO$58,349.63" -> "58349.63" -> Decimal (exacto, igual que NUMERIC en la BD)
            precio = Decimal(re.sub(r"[^\d.]", "", r["precio"]))
            rating = Decimal(r["rating"]) if r["rating"] else None
        except ArithmeticError:   # texto que no es número (Decimal lanza InvalidOperation)
            continue
        # Un precio por noche menor a 1.000 COP es un error del sitio (se observaron valores como CO$11.00)
        if precio < 1000:
            continue
        if rating is not None and not 0 <= rating <= 10:
            rating = None
        limpios.append({**r, "precio": precio, "rating": rating})
    return limpios


@task(retries=2, retry_delay_seconds=10)
def guardar(registros: list[dict], codigo: str) -> int:
    """Paso 4 (ingesta): guarda los registros en la BD de hoteles.
    UNA conexión y UNA transacción por ciudad con executemany (todas las filas en lote):
    abrir una conexión por fila es lo que saturaba la capa de persistencia en el sistema anterior.
    UPSERT (ON CONFLICT url DO UPDATE): si el hostal ya existe, solo se actualizan precio/rating."""
    with psycopg.connect(DB) as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO hoteles (nombre, ciudad, precio_noche, rating, url, fuente, actualizado)
            VALUES (%(nombre)s, %(ciudad)s, %(precio)s, %(rating)s, %(url)s, 'hostelworld', now())
            ON CONFLICT (url) DO UPDATE
               SET nombre = EXCLUDED.nombre,
                   precio_noche = EXCLUDED.precio_noche,
                   rating = EXCLUDED.rating,
                   actualizado = now()
            """,
            registros,
        )
    print(f"{codigo}: {len(registros)} hostales guardados/actualizados")
    return len(registros)


# ---------------------------------------------------------------- FLOW
# El flow orquesta las tareas. task_runner=DaskTaskRunner(...) = "ejecuta las tareas en el clúster de Dask".
@flow(
    name="ingesta-hoteles",
    task_runner=DaskTaskRunner(address=DASK_SCHEDULER),
    log_prints=True,   # los print() aparecen en los logs del panel de Prefect
)
def ingesta_hoteles(ciudades: list[str] = list(CIUDADES)):
    # .map() lanza UNA tarea por ciudad, todas en paralelo en los workers de Dask.
    # Se encadenan con "futures": estructurar(MDE) arranca apenas termina descargar(MDE),
    # sin esperar a las otras ciudades.
    htmls = descargar.map(ciudades)
    crudos = estructurar.map(htmls, ciudades)
    limpios = limpiar.map(crudos)
    guardados = guardar.map(limpios, ciudades)

    # Resumen: una ciudad que falle (tras agotar sus retries) no tumba a las demás
    total = 0
    for codigo, futuro in zip(ciudades, guardados):
        try:
            total += futuro.result()
        except Exception as e:
            print(f"{codigo}: falló definitivamente -> {e}")
    if total == 0:
        raise RuntimeError("No se pudo ingerir ninguna ciudad")   # el flow queda en estado Failed en el panel
    print(f"TOTAL: {total} hostales ingeridos")
    return total


if __name__ == "__main__":
    # serve() registra el flow en Prefect (aparece en la sección "Deployments" del panel),
    # lo programa cada 30 minutos ("capturar continuamente") y permite lanzarlo a mano con "Run".
    ingesta_hoteles.serve(name="hostelworld-cada-30-min", interval=timedelta(minutes=30))
