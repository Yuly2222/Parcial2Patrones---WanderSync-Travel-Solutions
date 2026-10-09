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
# Fuente 3: ofertas de Booking.com por categoría (alojamiento, vuelos, coches, atracciones), desde
#           páginas guardadas a mano: Booking responde con un desafío anti-bot (AWS WAF) incluso a su robots.txt,
#           así que no se intenta ninguna descarga automática (ver booking.py). Van a la BD del servicio Ofertas.
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
import booking   # fuente 3: ofertas de Booking desde páginas guardadas (ver booking.py)
import robots_cache   # robots.txt cacheado por worker (módulo aparte: ver por qué en robots_cache.py)

UA = "WanderSync-academic-bot/0.1 (proyecto universitario)"
BASE = "https://www.hostelworld.com"

# Código de ciudad (IATA, el mismo que usan las tablas de vuelos y autos) -> ruta de la ciudad en Hostelworld
# (/hostels/<ruta>/). Son destinos con vuelo desde Bogotá en la página de Booking que TAMBIÉN tienen alojamientos
# en Hostelworld: con vuelo + alojamiento hay paquete. (Cúcuta, Montería o Valledupar no entran: Hostelworld no
# tiene alojamientos allá.) Las rutas se tomaron de los enlaces del propio Hostelworld.
CIUDADES = {
    # Colombia
    "MDE": "south-america/colombia/medellin",
    "CTG": "south-america/colombia/cartagena",
    "SMR": "south-america/colombia/santa-marta",
    "CLO": "south-america/colombia/cali",
    "BAQ": "south-america/colombia/barranquilla",
    "BGA": "south-america/colombia/bucaramanga",
    "PEI": "south-america/colombia/pereira",
    "ADZ": "south-america/colombia/san-andres-island",
    "AXM": "south-america/colombia/armenia",
    "LET": "south-america/colombia/leticia",
    "RCH": "south-america/colombia/riohacha",
    "NVA": "south-america/colombia/neiva",
    "IBE": "south-america/colombia/ibague",
    "PSO": "south-america/colombia/pasto",
    # Latinoamérica y Norteamérica
    "LIM": "south-america/peru/lima",
    "UIO": "south-america/ecuador/quito",
    "BUE": "south-america/argentina/buenos-aires",
    "PTY": "north-america/panama/panama-city",
    "MEX": "north-america/mexico/mexico-city",
    "CUN": "north-america/mexico/cancun",
    "MIA": "north-america/usa/miami",
    "NYC": "north-america/usa/new-york",
    "ORL": "north-america/usa/orlando",
    "LAX": "north-america/usa/los-angeles",
    # Europa
    "MAD": "europe/spain/madrid",
    "BCN": "europe/spain/barcelona",
    "PAR": "europe/france/paris",
    "ROM": "europe/italy/rome",
    "LON": "europe/england/london",
    "AMS": "europe/netherlands/amsterdam",
}

DB = os.environ["DATABASE_URL"]                                  # BD "hoteles"
DASK_SCHEDULER = os.environ["DASK_SCHEDULER"]                    # tcp://dask-scheduler:8786
# Demo de retries: probabilidad (0 a 1) de simular un fallo de red al descargar. 0 = desactivado.
PROB_FALLO = float(os.environ.get("PROB_FALLO_SCRAPER", "0"))
# Carpeta con las páginas de Trivago guardadas a mano (montada como volumen: agregar una muestra no exige rebuild)
MUESTRAS_TRIVAGO = Path(os.environ.get("MUESTRAS_TRIVAGO", "muestras/trivago"))
# Páginas de ofertas de Booking: muestras/booking/recortadas/booking-<categoria>.html (las que se suben al repo)
# o, si no se han recortado, muestras/booking/booking-<categoria>.html tal como se guardaron
MUESTRAS_BOOKING = Path(os.environ.get("MUESTRAS_BOOKING", "muestras/booking"))
OFERTAS_DB = os.environ.get("OFERTAS_DATABASE_URL")              # BD del servicio Ofertas
# Los vuelos desde Bogotá y el precio medio de alquiler de autos de Booking también alimentan el catálogo
# de los servicios Vuelos y Autos: así hay paquetes reservables en todos los destinos de CIUDADES.
CATALOGO_DB = {"vuelos": os.environ.get("VUELOS_DATABASE_URL"), "coches": os.environ.get("AUTOS_DATABASE_URL")}


# ---------------------------------------------------------------- TAREAS
# @task convierte la función en una tarea de Prefect: queda registrada (estado, duración, logs)
# y, gracias al DaskTaskRunner del flow, se ejecuta en un worker de Dask y no en este contenedor.

class Bloqueado(RuntimeError):
    """El sitio rechazó al bot (403/429 o desafío anti-bot). No se evade ni se reintenta."""


HEADERS = {"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"}


def obtener_html(base: str, url: str) -> str:
    """Descarga responsable, común a todas las fuentes en vivo:
    lee robots.txt, se identifica honestamente y falla si el sitio se defiende."""
    headers = HEADERS

    # 1. Respetar robots.txt: si el sitio no permite esa ruta a los bots, no se descarga.
    # (robots_cache: se lee una vez por sitio y por worker cada 30 min, no una vez por ciudad)
    reglas = robots_cache.reglas(base, UA)
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
    return obtener_html(BASE, f"{BASE}/hostels/{CIUDADES[codigo]}/")


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
def estructurar_booking(html: str, categoria: str, archivo: str) -> list[dict]:
    """Paso 2 (estructuración) para Booking: página de ofertas guardada -> una oferta por destino."""
    ofertas = booking.parsear(html, categoria)
    print(f"Booking {booking.CATEGORIAS[categoria]}: {len(ofertas)} ofertas leídas de {archivo}")
    if not ofertas:
        raise ValueError(f"0 ofertas en {archivo}: ¿es la página de ofertas? ¿Booking cambió su HTML?")
    return ofertas


@task
def limpiar_ofertas(ofertas: list[dict]) -> list[dict]:
    """Paso 3 (limpieza) para ofertas: 'COP 325.300' -> Decimal(325300); descarta precios inválidos."""
    limpias = []
    for o in ofertas:
        precio = booking.precio_cop(o["precio"])
        if precio is None or precio < 1000:
            continue
        limpias.append({**o, "precio": Decimal(precio)})
    return limpias


@task(retries=2, retry_delay_seconds=10)
def guardar_ofertas(ofertas: list[dict], categoria: str) -> int:
    """Paso 4 (ingesta) en la BD del servicio Ofertas: UPSERT en lote por (categoria, llave), y se borran las
    ofertas de esa categoría que ya no están en la página (la sección refleja la página guardada más reciente).
    Todo en UNA transacción: quien consulta nunca ve la categoría a medio actualizar.
    retries: la primera vez, la tabla la crea el servicio Ofertas al arrancar; si la ingesta llega antes, reintenta."""
    with psycopg.connect(OFERTAS_DB) as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO ofertas (categoria, llave, destino, ciudad, titulo, detalle, cantidad, precio_desde, unidad, campana, url, actualizado)
            VALUES (%(categoria)s, %(llave)s, %(destino)s, %(ciudad)s, %(titulo)s, %(detalle)s, %(cantidad)s, %(precio)s, %(unidad)s, %(campana)s, %(url)s, now())
            ON CONFLICT (categoria, llave) DO UPDATE
               SET destino = EXCLUDED.destino, ciudad = EXCLUDED.ciudad, titulo = EXCLUDED.titulo,
                   detalle = EXCLUDED.detalle, cantidad = EXCLUDED.cantidad,
                   precio_desde = EXCLUDED.precio_desde, unidad = EXCLUDED.unidad,
                   campana = EXCLUDED.campana, url = EXCLUDED.url, actualizado = now()
            """,
            ofertas,
        )
        cur.execute(
            "DELETE FROM ofertas WHERE categoria = %s AND NOT (llave = ANY(%s))",
            (categoria, [o["llave"] for o in ofertas]),
        )
    print(f"Booking {booking.CATEGORIAS[categoria]}: {len(ofertas)} ofertas guardadas/actualizadas")
    return len(ofertas)


@task(retries=2, retry_delay_seconds=10)
def guardar_catalogo(ofertas: list[dict], categoria: str) -> int:
    """Paso 4b: las ofertas de Booking de ciudades del sistema pasan al catálogo reservable.
    vuelos -> tabla vuelos (BOG -> destino, precio por persona); coches -> tabla autos (precio medio al día).
    UPSERT por (origen, destino, fuente) / (ciudad, modelo): re-procesar actualiza el precio, no duplica."""
    if categoria == "vuelos":
        filas = [
            {"origen": booking.codigo_origen(o["titulo"]), "destino": o["ciudad"], "precio": o["precio"],
             "nombre": o["destino"], "pais": o["detalle"]}
            for o in ofertas if o["ciudad"] and booking.codigo_origen(o["titulo"])
        ]
        sql = """
            INSERT INTO vuelos (origen, destino, precio, destino_nombre, pais, fuente, actualizado)
            VALUES (%(origen)s, %(destino)s, %(precio)s, %(nombre)s, %(pais)s, 'booking-muestra', now())
            ON CONFLICT (origen, destino, fuente) DO UPDATE
               SET precio = EXCLUDED.precio, destino_nombre = EXCLUDED.destino_nombre, pais = EXCLUDED.pais,
                   actualizado = now()
        """
    else:
        filas = [
            {"ciudad": o["ciudad"], "modelo": "Auto estándar · precio medio en Booking", "precio": o["precio"]}
            for o in ofertas if o["ciudad"]
        ]
        sql = """
            INSERT INTO autos (modelo, ciudad, precio_dia, fuente, actualizado)
            VALUES (%(modelo)s, %(ciudad)s, %(precio)s, 'booking-muestra', now())
            ON CONFLICT (ciudad, modelo) DO UPDATE SET precio_dia = EXCLUDED.precio_dia, actualizado = now()
        """
    with psycopg.connect(CATALOGO_DB[categoria]) as conn, conn.cursor() as cur:
        cur.executemany(sql, filas)
    print(f"Catálogo {categoria}: {len(filas)} filas desde Booking")
    return len(filas)


@task
def limpiar(registros: list[dict]) -> list[dict]:
    """Paso 3 (limpieza): convierte textos a números y descarta datos inválidos."""
    limpios = []
    for r in registros:
        # Hostelworld muestra el precio en la moneda del visitante ("CO$58349.63"). Si llegara en otra moneda
        # (€, US$...), no se convierte a ojo: se descarta, para no guardar euros como si fueran pesos.
        if r["fuente"] == "hostelworld" and not r["precio"].strip().upper().startswith(("CO$", "COP")):
            continue
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
    # Solo para las ciudades que tienen página de destino conocida en Trivago (ver trivago.DESTINOS).
    ciudades_t = [c for c in ciudades if c in trivago.DESTINOS]
    htmls_t = descargar_trivago.map(ciudades_t)
    crudos_t = estructurar_trivago.map(htmls_t, ciudades_t, unmapped("en vivo"), unmapped("trivago"))
    guardados_t = guardar.map(limpiar.map(crudos_t), ciudades_t)

    # Resumen: una ciudad o fuente que falle (tras agotar sus retries) no tumba a las demás
    total = 0
    trivago_fallo = []
    for etiqueta, futuro in [*zip(ciudades, guardados), *((f"{c} (trivago)", g) for c, g in zip(ciudades_t, guardados_t))]:
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

    print(f"TOTAL: {total} alojamientos ingeridos (Hostelworld + Trivago)")

    # Fuente 3: ofertas de Booking, una cadena estructurar -> limpiar -> guardar por categoría, en paralelo en Dask.
    # Es independiente de los hoteles: se procesa aunque las fuentes de hoteles hayan fallado. Y un fallo aquí NO
    # marca el flow como fallido: las ofertas son un extra de la página, no parte de los paquetes.
    paginas = []
    for categoria in booking.CATEGORIAS:
        for archivo in (MUESTRAS_BOOKING / "recortadas" / f"booking-{categoria}.html", MUESTRAS_BOOKING / f"booking-{categoria}.html"):
            if archivo.exists():
                paginas.append((categoria, archivo.name, archivo.read_text(encoding="utf-8")))
                break
    if paginas and not OFERTAS_DB:
        print("Hay páginas de Booking pero falta OFERTAS_DATABASE_URL: no se guardan las ofertas")
    elif paginas:
        categorias = [p[0] for p in paginas]
        crudas = estructurar_booking.map([p[2] for p in paginas], categorias, [p[1] for p in paginas])
        limpias = limpiar_ofertas.map(crudas)
        guardadas = guardar_ofertas.map(limpias, categorias)
        # vuelos y coches de ciudades del sistema -> catálogo de los servicios Vuelos y Autos (en paralelo)
        catalogo = [
            (c, guardar_catalogo.submit(l, c)) for c, l in zip(categorias, limpias) if CATALOGO_DB.get(c)
        ]
        ofertas = 0
        for categoria, futuro in zip(categorias, guardadas):
            try:
                ofertas += futuro.result()
            except Exception as e:
                print(f"Booking {categoria}: falló -> {e}")
        for categoria, futuro in catalogo:
            try:
                futuro.result()
            except Exception as e:
                print(f"Catálogo {categoria}: falló -> {e}")
        faltan = [c for c in booking.CATEGORIAS if c not in categorias]
        print(f"OFERTAS: {ofertas} ofertas de Booking en {len(categorias)} categorías"
              + (f" (sin página guardada: {', '.join(faltan)})" if faltan else ""))

    if total == 0:
        raise RuntimeError("No se pudo ingerir ninguna ciudad")   # el flow queda en estado Failed en el panel
    return total


if __name__ == "__main__":
    # serve() registra el flow en Prefect (aparece en la sección "Deployments" del panel),
    # lo programa cada 30 minutos ("capturar continuamente") y permite lanzarlo a mano con "Run".
    ingesta_hoteles.serve(name="hostelworld-cada-30-min", interval=timedelta(minutes=30))
