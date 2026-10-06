# MÓDULO DE INGESTA: scraping real + Dask (ejecución distribuida) + Prefect (orquestación y observabilidad).
#
#   Prefect = el "capataz": define el flujo, programa cada cuánto corre, reintenta lo que falla
#             y muestra todo en su panel (http://localhost:4200).
#   Dask    = la "cuadrilla": un scheduler que reparte las tareas entre varios workers
#             (contenedores dask-worker) que las ejecutan EN PARALELO (panel: http://localhost:8787).
#
# Fuente 1: Hostelworld (plataforma comercial real de reservas de hostales), descargada en vivo.
#           Su robots.txt PERMITE las páginas de ciudad (/hostels/...) y no responde con desafíos anti-bot.
# Fuente 2: Trivago (trivago.com.co), descargado en vivo: páginas de destino /es-CO/odr/..., que su
#           robots.txt permite (ver trivago.py). Si Trivago bloquea al bot en una ciudad, se usa como
#           RESPALDO la página de esa ciudad guardada a mano en muestras/trivago/.
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
from pathlib import Path

import httpx
import psycopg
from bs4 import BeautifulSoup     # parser de HTML
# Parser de robots.txt que cumple el estándar RFC 9309 (el que usa Scrapy).
# NO se usa urllib.robotparser (librería estándar) porque es antiguo: no entiende comodines (* y $)
# y convierte la regla "Disallow: /s?" en "Disallow: /s", bloqueando por error todas las rutas /st/...
from protego import Protego
from prefect import flow, task, unmapped
from prefect_dask import DaskTaskRunner

import trivago   # fuente 2: Trivago, descarga en vivo + muestras guardadas de respaldo (ver trivago.py)

UA = "WanderSync-academic-bot/0.1 (proyecto universitario)"
BASE = "https://www.hostelworld.com"

# Código de ciudad (el mismo que usan las tablas de vuelos y autos) -> nombre de la ciudad en la URL del sitio
CIUDADES = {"MDE": "medellin", "CTG": "cartagena", "SMR": "santa-marta"}

DB = os.environ["DATABASE_URL"]                                  # BD "hoteles"
DASK_SCHEDULER = os.environ["DASK_SCHEDULER"]                    # tcp://dask-scheduler:8786
# Demo de retries: probabilidad (0 a 1) de simular un fallo de red al descargar. 0 = desactivado.
PROB_FALLO = float(os.environ.get("PROB_FALLO_SCRAPER", "0"))
# Carpeta con las páginas de Trivago guardadas a mano (montada como volumen: agregar una muestra no exige rebuild)
MUESTRAS_TRIVAGO = Path(os.environ.get("MUESTRAS_TRIVAGO", "muestras/trivago"))


# ---------------------------------------------------------------- TAREAS
# @task convierte la función en una tarea de Prefect: queda registrada (estado, duración, logs)
# y, gracias al DaskTaskRunner del flow, se ejecuta en un worker de Dask y no en este contenedor.

class Bloqueado(RuntimeError):
    """El sitio rechazó al bot (403/429 o desafío anti-bot). No se evade ni se reintenta."""


def obtener_html(base: str, url: str) -> str:
    """Descarga responsable, común a todas las fuentes en vivo:
    lee robots.txt, se identifica honestamente y falla si el sitio se defiende."""
    headers = {"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"}

    # 1. Respetar robots.txt: si el sitio no permite esa ruta a los bots, no se descarga.
    robots = httpx.get(f"{base}/robots.txt", headers=headers, timeout=15)
    reglas = Protego.parse(robots.text)
    if not reglas.can_fetch(url, UA):
        raise PermissionError(f"robots.txt no permite descargar {url}")

    # 2. Fallo simulado (solo si PROB_FALLO_SCRAPER > 0): para ver los retries en el panel de Prefect.
    if random.random() < PROB_FALLO:
        raise ConnectionError("Fallo de red simulado (demo de retries)")

    # 3. Descarga real
    r = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
    if r.status_code in (401, 403, 429):
        # Un rechazo explícito NO es un fallo de red: reintentar sería insistir contra la voluntad del sitio
        raise Bloqueado(f"El sitio rechazó la descarga (HTTP {r.status_code}); no se evade")
    r.raise_for_status()   # 5xx -> excepción -> Prefect reintenta

    # 4. Si el sitio nos pone un desafío anti-bot, fallamos honestamente en vez de intentar evadirlo.
    if trivago.ANTI_BOT.search(r.text):
        raise Bloqueado("El sitio respondió con un desafío anti-bot; no se evade")
    return r.text


# retries=3 + retry_delay_seconds: si falla, Prefect la reintenta 3 veces esperando 5s, 15s y 45s
# (backoff: cada espera es mayor, para no saturar un sitio que quizá está caído).
# retry_condition_fn: un bloqueo (Bloqueado / PermissionError) NO se reintenta; un error de red sí.
def _reintentable(task, task_run, state) -> bool:
    try:
        state.result()
    except (Bloqueado, PermissionError):
        return False
    except Exception:
        return True
    return False


@task(retries=3, retry_delay_seconds=[5, 15, 45], retry_condition_fn=_reintentable)
def descargar(codigo: str) -> str:
    """Paso 1 (scraping): descarga el HTML de la página de hostales de una ciudad en Hostelworld."""
    return obtener_html(BASE, f"{BASE}/hostels/south-america/colombia/{CIUDADES[codigo]}/")


@task(retries=3, retry_delay_seconds=[5, 15, 45], retry_condition_fn=_reintentable)
def descargar_trivago(codigo: str) -> str:
    """Paso 1 (scraping) en Trivago: descarga la página de destino de una ciudad (/es-CO/odr/...),
    permitida por su robots.txt. Los hoteles vienen en el HTML del servidor: basta BeautifulSoup."""
    return obtener_html(trivago.BASE, trivago.BASE + trivago.DESTINOS[codigo])


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
            "fuente": "hostelworld",
        }
    return list(hostales.values())


@task
def estructurar_trivago(html: str, codigo: str, origen: str, fuente: str) -> list[dict]:
    """Paso 2 (estructuración) para Trivago con BeautifulSoup: HTML -> registros.
    Sirve para la página descargada en vivo (fuente="trivago") y para una muestra guardada a mano
    (fuente="trivago-muestra"). Corre en un worker de Dask; después pasa por los mismos limpiar() y guardar()."""
    registros = trivago.parsear(html, codigo, fuente)
    print(f"{codigo}: {len(registros)} alojamientos leídos de Trivago ({origen})")
    if not registros:
        # Página descargada pero sin hoteles reconocibles: Trivago cambió su HTML -> que se note en Prefect
        raise ValueError(f"{codigo}: 0 hoteles en Trivago ({origen}); revisar los selectores de trivago.py")
    return registros


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
            VALUES (%(nombre)s, %(ciudad)s, %(precio)s, %(rating)s, %(url)s, %(fuente)s, now())
            ON CONFLICT (url) DO UPDATE
               SET nombre = EXCLUDED.nombre,
                   precio_noche = EXCLUDED.precio_noche,
                   rating = EXCLUDED.rating,
                   actualizado = now()
            """,
            registros,
        )
    print(f"{codigo}: {len(registros)} alojamientos guardados/actualizados")
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

    # Fuente 2: Trivago en vivo, la misma cadena de 4 tareas por ciudad, en paralelo con Hostelworld.
    # unmapped(...) = el mismo valor para todas las ciudades (no se reparte elemento a elemento).
    htmls_t = descargar_trivago.map(ciudades)
    crudos_t = estructurar_trivago.map(htmls_t, ciudades, unmapped("en vivo"), unmapped("trivago"))
    guardados_t = guardar.map(limpiar.map(crudos_t), ciudades)

    # Resumen: una ciudad o fuente que falle (tras agotar sus retries) no tumba a las demás
    total = 0
    trivago_fallo = []
    for etiqueta, futuro in [*zip(ciudades, guardados), *((f"{c} (trivago)", g) for c, g in zip(ciudades, guardados_t))]:
        try:
            total += futuro.result()
        except Exception as e:
            print(f"{etiqueta}: falló definitivamente -> {e}")
            if etiqueta.endswith("(trivago)"):
                trivago_fallo.append(etiqueta[:3])

    # RESPALDO: para cada ciudad donde Trivago en vivo falló (bloqueo, red, HTML cambiado), se usa la página
    # guardada a mano en muestras/trivago/ (nombre con el código de ciudad al inicio: MDE-medellin.html).
    # Se leen aquí y su HTML viaja a los workers de Dask, así los workers no necesitan acceso a la carpeta.
    respaldo = []
    for archivo in sorted(MUESTRAS_TRIVAGO.glob("*.html")):
        codigo = archivo.name[:3].upper()
        if codigo in trivago_fallo:
            respaldo.append((codigo, archivo.name, archivo.read_text(encoding="utf-8")))
    if respaldo:
        codigos_r = [m[0] for m in respaldo]
        crudos_r = estructurar_trivago.map(
            [m[2] for m in respaldo], codigos_r, [f"muestra guardada {m[1]}" for m in respaldo], unmapped("trivago-muestra")
        )
        for codigo, futuro in zip(codigos_r, guardar.map(limpiar.map(crudos_r), codigos_r)):
            try:
                total += futuro.result()
            except Exception as e:
                print(f"{codigo} (muestra de Trivago): falló -> {e}")
    sin_respaldo = sorted(set(trivago_fallo) - {m[0] for m in respaldo})
    if sin_respaldo:
        print(f"Trivago sin datos para {sin_respaldo}: no hay muestra guardada de respaldo (ver muestras/trivago/LEEME.md)")

    if total == 0:
        raise RuntimeError("No se pudo ingerir ninguna ciudad")   # el flow queda en estado Failed en el panel
    print(f"TOTAL: {total} alojamientos ingeridos (Hostelworld + Trivago)")
    return total


if __name__ == "__main__":
    # serve() registra el flow en Prefect (aparece en la sección "Deployments" del panel),
    # lo programa cada 30 minutos ("capturar continuamente") y permite lanzarlo a mano con "Run".
    ingesta_hoteles.serve(name="hostelworld-cada-30-min", interval=timedelta(minutes=30))
