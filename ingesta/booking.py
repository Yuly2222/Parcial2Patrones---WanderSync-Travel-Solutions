# FUENTE 3: ofertas de Booking.com, desde páginas GUARDADAS A MANO en el navegador.
#
# ¿Por qué no se descargan? Booking responde con un desafío anti-bot (AWS WAF, HTTP 202) incluso a su
# robots.txt. El estándar RFC 9309 dice que si el robots.txt no se puede leer, el bot debe asumir que no
# tiene permiso; y el proyecto no evade bloqueos. Así que no se intenta ninguna descarga automática:
# una persona abre la página en su navegador, la guarda, y este módulo la procesa (scraping del HTML guardado).
#
# Archivos: muestras/booking/booking-<categoria>.html. Cada pestaña de Booking tiene una página distinta,
# así que hay UN PARSER POR CATEGORÍA. Todos usan atributos estables (data-testid, role, nombres de módulo,
# datos JSON embebidos) y el ORDEN de los textos; nunca las clases CSS ofuscadas ("c3bdfd4ac2"...).
import json
import re
import unicodedata
from urllib.parse import parse_qs, urlencode, urlparse

from bs4 import BeautifulSoup

CATEGORIAS = {
    "alojamiento": "Alojamiento",
    "vuelos": "Vuelos",
    "coches": "Alquiler de coches",
    "atracciones": "Atracciones",
}

# Nombre de ciudad (normalizado) -> código IATA, el mismo de las tablas de vuelos, hoteles y autos.
# Los vuelos traen su código en el JSON de la página; este mapa da el código a las ofertas de alojamiento, coches
# y atracciones (que solo traen el nombre) para poder enlazarlas con los paquetes y con el catálogo de autos.
# Son los 50 destinos de la página "Vuelos desde Bogotá", más los nombres alternos que usa Booking.
_CIUDADES = {
    "medellin": "MDE", "cartagena": "CTG", "cartagena de indias": "CTG", "santa marta": "SMR",
    "cali": "CLO", "barranquilla": "BAQ", "bucaramanga": "BGA", "pereira": "PEI", "san andres": "ADZ",
    "cucuta": "CUC", "armenia": "AXM", "monteria": "MTR", "leticia": "LET", "riohacha": "RCH",
    "valledupar": "VUP", "neiva": "NVA", "ibague": "IBE", "pasto": "PSO", "ipiales": "IPI", "bogota": "BOG",
    "madrid": "MAD", "barcelona": "BCN", "valencia": "VLC", "paris": "PAR", "roma": "ROM", "londres": "LON",
    "amsterdam": "AMS", "frankfurt": "FRA", "bruselas": "BRU", "zurich": "ZRH", "varsovia": "WAW",
    "miami": "MIA", "orlando": "ORL", "nueva york": "NYC", "fort lauderdale": "FLL", "los angeles": "LAX",
    "toronto": "YTO", "montreal": "YMQ", "ciudad de mexico": "MEX", "cancun": "CUN", "punta cana": "PUJ",
    "santo domingo": "SDQ", "panama": "PTY", "ciudad de panama": "PTY", "san jose": "SJO", "guatemala": "GUA",
    "lima": "LIM", "quito": "UIO", "buenos aires": "BUE", "santiago": "SCL", "rio de janeiro": "RIO",
    "sao paulo": "SAO", "caracas": "CCS",
}
# Orígenes de vuelo reconocidos (la página "Vuelos desde Bogotá" trae el origen en el <title>)
ORIGENES = {"bogota": "BOG"}

# Precio en cualquiera de los formatos que usa Booking: "COP 325.300", "189.544 COP", "COP 229.120"
_PRECIO = re.compile(r"COP\s?\d[\d.]*|\d[\d.]*\s?COP")
_CANTIDAD = re.compile(r"^(\d[\d.]*)\s+ofertas?\b", re.I)


def _normalizar(texto: str) -> str:
    """'Medellín' -> 'medellin' (sin tildes, minúsculas) para comparar nombres."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def codigo_ciudad(destino: str | None) -> str | None:
    return _CIUDADES.get(_normalizar(destino)) if destino else None


def codigo_origen(titulo: str | None) -> str | None:
    """'Bogotá → Medellín' -> 'BOG'."""
    if not titulo or "→" not in titulo:
        return None
    return ORIGENES.get(_normalizar(titulo.split("→")[0]))


def precio_cop(texto: str) -> int | None:
    """'COP 325.300' / '189.544 COP' -> 325300 / 189544 (el punto separa miles). '51597.63' -> 51598."""
    t = texto.strip()
    if re.fullmatch(r"\d+(\.\d{1,2})?", t):          # formato máquina (JSON)
        return round(float(t))
    digitos = re.sub(r"\D", "", t.split(",")[0])
    return int(digitos) if digitos else None


# Parámetros del enlace que sí describen la oferta. Se descartan los de rastreo/afiliado (aid, label, sid...).
_PARAMS_UTILES = ("dest_id", "dest_type", "checkin", "checkout")


def url_limpia(enlace: str | None) -> str | None:
    if not enlace:
        return None
    u = urlparse(enlace)
    q = parse_qs(u.query)
    params = urlencode({k: q[k][0] for k in _PARAMS_UTILES if k in q})
    return f"{u.scheme}://{u.netloc}{u.path}" + (f"?{params}" if params else "")


def _oferta(categoria, llave, destino, precio, *, titulo=None, detalle=None, cantidad=None, unidad=None, campana=None, url=None):
    return {
        "categoria": categoria,
        "llave": llave,
        "destino": destino,
        "ciudad": codigo_ciudad(destino),
        "titulo": titulo,
        "detalle": detalle,
        "cantidad": cantidad,
        "precio": precio,
        "unidad": unidad,
        "campana": campana,
        "url": url_limpia(url),
    }


def _i_precio(textos: list[str]) -> int | None:
    return next((i for i, t in enumerate(textos) if _PRECIO.search(t)), None)


# ---------------------------------------------------------------- Alojamiento (página de ofertas)
# <div data-testid="card-deal">: "318 Ofertas de finales de año" · "Madrid" · "Desde" · "COP 325.300" · "por noche"
def _alojamiento(soup) -> list[dict]:
    titulo = soup.select_one('[data-testid="deals-header-title"]')
    campana = titulo.get_text(" ", strip=True) if titulo else None
    ofertas = []
    for tarjeta in soup.select('[data-testid="card-deal"]'):
        textos = list(tarjeta.stripped_strings)
        i = _i_precio(textos)
        if i is None:
            continue
        cantidad = next((int(m.group(1).replace(".", "")) for t in textos if (m := _CANTIDAD.match(t))), None)
        destino = next((t for t in textos[:i] if not _CANTIDAD.match(t) and _normalizar(t) not in ("desde", "a partir de")), None)
        if not destino:
            continue
        enlace = tarjeta.select_one("a[href]")
        url = enlace["href"] if enlace else None
        q = parse_qs(urlparse(url).query) if url else {}
        llave = q["dest_id"][0] if q.get("dest_id") else _normalizar(destino)
        ofertas.append(_oferta("alojamiento", llave, destino, _PRECIO.search(textos[i]).group(0),
                               cantidad=cantidad, unidad=textos[i + 1] if i + 1 < len(textos) else None,
                               campana=campana, url=url))
    return ofertas


# ---------------------------------------------------------------- Vuelos ("Cualquier destino")
# La página pinta solo 10 tarjetas, pero trae TODOS los destinos (50 desde Bogotá) en el estado inicial de su
# aplicación: <script> window.__INITIAL_STATE__ = {..., "flyAnywhere": {"fromCity": {...}, "results": [...]}}.
# Cada resultado: toCity.iata ("MDE"), toCity.translatedCityName ("Medellín"), toCity.translatedCountryName
# ("Colombia") y price.units (precio por persona en COP). Si ese JSON no está, se leen las tarjetas visibles.
_ESTADO = re.compile(r"window\.__INITIAL_STATE__\s*=\s*")


def estado_inicial(soup) -> dict | None:
    for script in soup.find_all("script"):
        texto = script.string or ""
        m = _ESTADO.search(texto)
        if m:
            try:
                return json.JSONDecoder().raw_decode(texto[m.end():])[0]
            except ValueError:
                return None
    return None


def _vuelos_json(fly: dict) -> list[dict]:
    origen = (fly.get("fromCity") or {}).get("translatedCityName")
    campana = f"Vuelos desde {origen}" if origen else "Vuelos a cualquier destino"
    ofertas = {}
    for r in fly.get("results") or []:
        ciudad, precio = r.get("toCity") or {}, (r.get("price") or {}).get("units")
        destino = ciudad.get("translatedCityName") or ciudad.get("name")
        if not (destino and precio):
            continue
        oferta = _oferta("vuelos", _normalizar(destino), destino, str(precio),
                         titulo=f"{origen} → {destino}" if origen else None,
                         detalle=ciudad.get("translatedCountryName"), unidad="por persona", campana=campana)
        oferta["ciudad"] = ciudad.get("iata") or oferta["ciudad"]   # el JSON trae el código IATA
        ofertas[oferta["llave"]] = oferta
    return list(ofertas.values())


# Respaldo: tarjetas role="button" del módulo FlyAnywhereCardsListItem ("Medellín" · "Colombia" · "189.544 COP" ·
# "por persona"); el origen está en el <title>: "Bogotá – Cualquier destino - Booking.com"
def _vuelos(soup) -> list[dict]:
    fly = (estado_inicial(soup) or {}).get("flyAnywhere") or {}
    if fly.get("results"):
        return _vuelos_json(fly)
    titulo = soup.title.get_text(" ", strip=True) if soup.title else ""
    origen = re.split(r"\s[–-]\s", titulo)[0].strip() if "–" in titulo or " - " in titulo else None
    campana = f"Vuelos desde {origen}" if origen else "Vuelos a cualquier destino"
    ofertas = []
    for tarjeta in soup.select('[role="button"][class*="FlyAnywhereCardsListItem"]'):
        textos = list(tarjeta.stripped_strings)
        i = _i_precio(textos)
        if i is None or i == 0:
            continue
        destino = textos[0]
        pais = textos[1] if i >= 2 else None
        ofertas.append(_oferta("vuelos", _normalizar(destino), destino, _PRECIO.search(textos[i]).group(0),
                               titulo=f"{origen} → {destino}" if origen else None, detalle=pais,
                               unidad=textos[i + 1] if i + 1 < len(textos) else None, campana=campana))
    return ofertas


# ---------------------------------------------------------------- Alquiler de coches
# <div data-testid="in-product-interlinking-item">: "Medellín" · "8 puntos de alquiler de coches" ·
#   "Precio medio de" · "COP 229.120" · "al día"   + enlace /cars/city/co/medellin...
def _coches(soup) -> list[dict]:
    ofertas = {}
    for item in soup.select('[data-testid="in-product-interlinking-item"]'):
        textos = list(item.stripped_strings)
        i = _i_precio(textos)
        if i is None or i == 0:
            continue
        destino = textos[0]
        enlace = item.select_one("a[href]") or item.find_parent("a", href=True)
        url = enlace["href"] if enlace else None
        llave = urlparse(url).path.rsplit("/", 1)[-1].split(".")[0] if url else _normalizar(destino)
        detalle = next((t for t in textos[1:i] if "punto" in t.lower()), None)
        ofertas[llave] = _oferta("coches", llave, destino, _PRECIO.search(textos[i]).group(0),
                                 detalle=detalle, unidad=textos[i + 1] if i + 1 < len(textos) else None,
                                 campana="Precio medio de alquiler por día", url=url)
    return list(ofertas.values())


# ---------------------------------------------------------------- Atracciones
# La página guarda sus productos en un JSON embebido (<script data-capla-store-data="apollo">), con entradas
# "AttractionsProduct": name, ufiDetails.bCityName (ciudad), representativePrice.publicAmount (precio en COP).
def _atracciones(soup) -> list[dict]:
    ofertas = {}
    for script in soup.select('script[data-capla-store-data="apollo"]'):
        try:
            datos = json.loads(script.string or "")
        except ValueError:
            continue
        for valor in (datos.values() if isinstance(datos, dict) else []):
            if not isinstance(valor, dict) or valor.get("__typename") != "AttractionsProduct":
                continue
            precio = (valor.get("representativePrice") or {}).get("publicAmount")
            ciudad = (valor.get("ufiDetails") or {}).get("bCityName")
            if not (precio and ciudad and valor.get("name")):
                continue
            slug = valor.get("slug") or _normalizar(valor["name"])
            ofertas[slug] = _oferta("atracciones", slug, ciudad, str(precio), titulo=valor["name"],
                                    unidad="por persona", campana="Atracciones recomendadas")
    return list(ofertas.values())


_PARSERS = {"alojamiento": _alojamiento, "vuelos": _vuelos, "coches": _coches, "atracciones": _atracciones}


def parsear(html: str, categoria: str) -> list[dict]:
    """Extrae las ofertas de una página de Booking guardada, con el parser de su categoría."""
    return _PARSERS[categoria](BeautifulSoup(html, "html.parser"))


def recortar(html: str, categoria: str) -> str:
    """Reduce la página guardada (0,3 a 1,2 MB + carpeta _files) a lo único que usa su parser."""
    soup = BeautifulSoup(html, "html.parser")
    partes = []
    if categoria == "atracciones":
        # Solo los productos del JSON embebido, con los campos que usa el parser
        productos = {}
        for script in soup.select('script[data-capla-store-data="apollo"]'):
            try:
                datos = json.loads(script.string or "")
            except ValueError:
                continue
            for k, v in (datos.items() if isinstance(datos, dict) else []):
                if isinstance(v, dict) and v.get("__typename") == "AttractionsProduct":
                    productos[k] = {
                        "__typename": "AttractionsProduct", "name": v.get("name"), "slug": v.get("slug"),
                        "representativePrice": {"publicAmount": (v.get("representativePrice") or {}).get("publicAmount")},
                        "ufiDetails": {"bCityName": (v.get("ufiDetails") or {}).get("bCityName")},
                    }
        partes.append('<script type="application/json" data-capla-store-data="apollo">'
                      + json.dumps(productos, ensure_ascii=False) + "</script>")
    elif categoria == "vuelos" and ((estado_inicial(soup) or {}).get("flyAnywhere") or {}).get("results"):
        # Solo el estado inicial con los campos que usa el parser (de ~0,9 MB a unos KB)
        fly = estado_inicial(soup)["flyAnywhere"]
        minimo = {"flyAnywhere": {
            "fromCity": {k: (fly.get("fromCity") or {}).get(k) for k in ("iata", "translatedCityName")},
            "results": [
                {"toCity": {k: (r.get("toCity") or {}).get(k) for k in ("iata", "name", "translatedCityName", "translatedCountryName")},
                 "price": {"units": (r.get("price") or {}).get("units"), "currencyCode": (r.get("price") or {}).get("currencyCode")}}
                for r in fly.get("results") or []
            ],
        }}
        if soup.title:
            partes.append(f"<title>{soup.title.get_text(strip=True)}</title>")
        partes.append("<script>window.__INITIAL_STATE__ = " + json.dumps(minimo, ensure_ascii=False) + ";</script>")
    else:
        if soup.title:
            partes.append(f"<title>{soup.title.get_text(strip=True)}</title>")
        titulo = soup.select_one('[data-testid="deals-header-title"]')
        if titulo:
            partes.append(f'<h1 data-testid="deals-header-title">{titulo.get_text(" ", strip=True)}</h1>')
        selector = {
            "alojamiento": '[data-testid="card-deal"]',
            "vuelos": '[role="button"][class*="FlyAnywhereCardsListItem"]',
            "coches": '[data-testid="in-product-interlinking-item"]',
        }[categoria]
        for el in soup.select(selector):
            for basura in el.select("picture, img, svg, script, style"):
                basura.decompose()
            for hijo in [el, *el.find_all(True)]:
                clase = " ".join(hijo.get("class", []))
                hijo.attrs.pop("style", None)
                # se conserva solo el nombre de módulo que usa el selector de vuelos; el resto de clases se quita
                hijo.attrs.pop("class", None)
                if "FlyAnywhereCardsListItem" in clase and hijo is el:
                    hijo["class"] = "FlyAnywhereCardsListItem"
            partes.append(str(el))
    return "<!-- Muestra recortada de una página de Booking guardada desde el navegador -->\n" + "\n".join(partes) + "\n"


if __name__ == "__main__":
    # Uso: python booking.py muestras/booking/booking-vuelos.html
    #  -> deja la versión recortada en muestras/booking/recortadas/booking-vuelos.html
    import sys
    from pathlib import Path

    for ruta in sys.argv[1:]:
        origen = Path(ruta)
        categoria = origen.stem.removeprefix("booking-")
        if categoria not in CATEGORIAS:
            print(f"{origen.name}: el nombre debe ser booking-<categoria>.html con categoria en {list(CATEGORIAS)}")
            continue
        destino = origen.parent / "recortadas" / origen.name
        destino.parent.mkdir(exist_ok=True)
        recortada = recortar(origen.read_text(encoding="utf-8"), categoria)
        destino.write_text(recortada, encoding="utf-8")
        ofertas = parsear(recortada, categoria)
        print(f"{destino}: {len(ofertas)} ofertas de {CATEGORIAS[categoria]}")
        for o in ofertas[:4]:
            print(f"   {o['titulo'] or o['destino']} ({o['ciudad'] or '-'}) · {o['precio']} {o['unidad'] or ''}")
