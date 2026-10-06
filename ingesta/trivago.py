# FUENTE 2: Trivago (trivago.com.co), descargado con httpx y parseado con BeautifulSoup.
#
# ¿Qué páginas se descargan? Las PÁGINAS DE DESTINO /es-CO/odr/hoteles-<ciudad>?search=200-<id>.
# Su robots.txt SÍ las permite: prohíbe /*/srl/ (resultados de búsqueda), /hotel/ y las imágenes,
# pero no /es-CO/odr/ (aparecen además en su sitemap de destinos, es decir, quieren que se indexen).
# Antes de cada descarga se vuelve a leer robots.txt con protego: si Trivago cambia sus reglas, la tarea
# se detiene sola.
#
# ¿Por qué BeautifulSoup y no Selenium? Estas páginas llegan con los hoteles ya escritos en el HTML del
# servidor, así que no hace falta ejecutar JavaScript ni abrir un navegador. BeautifulSoup es un parser:
# no ayuda a "esquivar" bloqueos, que dependen de la petición HTTP y no del parser. Si Trivago responde
# 403 o un desafío anti-bot, la tarea FALLA (no se evade) y el flow usa como respaldo las páginas
# guardadas a mano en muestras/trivago/.
#
# Selectores: atributos ESTABLES, nunca las clases CSS ("_8AwSku", "QLXoPy"...) que Trivago regenera
# en cada despliegue:
#   1. microdatos de schema.org (itemtype=".../Hotel", itemprop="name" / "price" / "ratingValue")
#   2. el enlace de cada hotel: /oar/...?search=100-<id> (el id identifica al alojamiento)
#   3. bloques JSON-LD (<script type="application/ld+json">) de tipo Hotel
import json
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

BASE = "https://www.trivago.com.co"

# Código de ciudad del sistema -> página de destino en Trivago (ids tomados del propio sitio)
DESTINOS = {
    "MDE": "/es-CO/odr/hoteles-medell%C3%ADn-colombia?search=200-65524",
    "CTG": "/es-CO/odr/hoteles-cartagena-colombia?search=200-65529",
    "SMR": "/es-CO/odr/hoteles-santa-marta-colombia?search=200-65542",
}

# Señales de que el sitio respondió con un desafío anti-bot en vez de la página
ANTI_BOT = re.compile(r"awswaf|captcha|cf-chl|datadome|px-captcha|perimeterx|access denied", re.I)

_ID_HOTEL = re.compile(r"search=100-(\d+)")
_PRECIO_COP = re.compile(r"\$\s?\d{1,3}(?:\.\d{3})+|\$\s?\d{4,}")   # "$ 866.899" o "$866899"
_RATING = re.compile(r"\b(10|[0-9])[.,](\d)\b")                      # "8,4" o "8.4"


def precio_cop(texto: str | None) -> int | None:
    """'$ 1.024.473' -> 1024473. En formato colombiano el punto separa MILES, no decimales.
    Un atributo content="866899.00" (formato máquina) sí trae punto decimal."""
    if not texto:
        return None
    t = texto.strip()
    if re.fullmatch(r"\d+(\.\d{1,2})?", t):          # formato máquina: 866899 o 866899.5
        return int(float(t))
    digitos = re.sub(r"\D", "", t)                    # formato visible: $ 866.899
    return int(digitos) if digitos else None


def _rating(texto: str | None) -> str | None:
    """'7,8' / '7.8' -> '7.8' (0 a 10)."""
    if not texto:
        return None
    m = _RATING.search(texto)
    return f"{m.group(1)}.{m.group(2)}" if m else None


def _valor(el) -> str | None:
    """Texto de un elemento con itemprop: en <meta> está en content, en el resto es el texto visible."""
    if el is None:
        return None
    return el.get("content") or el.get_text(" ", strip=True) or None


def _id_de(el) -> str | None:
    """Id de Trivago del alojamiento: data-accommodation de un ancestro o el search=100-<id> de un enlace."""
    for anc in [el, *el.parents]:
        if getattr(anc, "get", None) and anc.get("data-accommodation"):
            return anc["data-accommodation"]
    enlace = el if el.name == "a" else el.select_one('a[href*="search=100-"]')
    if enlace and (m := _ID_HOTEL.search(enlace.get("href", ""))):
        return m.group(1)
    return None


def _desde_tarjeta(tarjeta, codigo: str, fuente: str, id_hotel: str | None = None) -> dict | None:
    """Extrae nombre, precio más barato y rating de una tarjeta de hotel."""
    id_hotel = id_hotel or _id_de(tarjeta)
    nombre = _valor(
        tarjeta.select_one('[data-testid="item-name"]')
        or tarjeta.select_one('[itemprop="name"]')
    )
    if not nombre:
        enlace = tarjeta.select_one('a[href*="/oar/"]')
        nombre = enlace.get_text(" ", strip=True) if enlace else None
    if not nombre:
        img = tarjeta.select_one("img[alt]")
        nombre = img["alt"].split("(")[0].strip() if img else None   # alt="227 Condo by IONICA, (Miami, ...)"

    # Cada hotel puede traer VARIAS ofertas de distintos partners: se guarda la más barata
    precios = [precio_cop(_valor(p)) for p in tarjeta.select('[itemprop="price"], [data-testid="recommended-price"]')]
    if not any(precios):
        precios = [precio_cop(m) for m in _PRECIO_COP.findall(tarjeta.get_text(" ", strip=True))]
    precios = [p for p in precios if p]

    rating = _rating(_valor(tarjeta.select_one('meta[itemprop="ratingValue"]') or tarjeta.select_one('[itemprop="ratingValue"]')))
    if rating is None:
        sec = tarjeta.select_one('[data-testid*="rating"]')
        rating = _rating(sec.get_text(" ", strip=True)) if sec else None
    if rating is None:
        # Último recurso: una calificación "8,6" en el texto de la tarjeta, quitando antes los precios
        rating = _rating(_PRECIO_COP.sub(" ", tarjeta.get_text(" ", strip=True)))

    if not (id_hotel and nombre and precios):
        return None
    return {
        "url": f"trivago:{id_hotel}",        # llave del UPSERT: el id de Trivago no cambia aunque cambie el precio
        "ciudad": codigo,
        "nombre": nombre.rstrip(",").strip(),
        "precio": str(min(precios)),
        "rating": rating,
        "fuente": fuente,
    }


def _tarjeta_del_enlace(enlace):
    """Sube desde el enlace de un hotel hasta el contenedor más pequeño que tenga precio,
    sin pasarse a un contenedor que agrupe a OTROS hoteles."""
    propio = _ID_HOTEL.search(enlace["href"]).group(1)
    anterior = enlace
    for anc in enlace.parents:
        if anc.name in ("body", "html", "[document]"):
            break
        ids = {m.group(1) for a in anc.select('a[href*="search=100-"]') if (m := _ID_HOTEL.search(a["href"]))}
        if ids - {propio}:
            return anterior if _PRECIO_COP.search(anterior.get_text(" ")) else None
        if _PRECIO_COP.search(anc.get_text(" ")):
            return anc
        anterior = anc
    return None


def _json_ld(soup, codigo: str, fuente: str) -> list[dict]:
    """Hoteles declarados en bloques JSON-LD de schema.org (si la página los trae)."""
    registros = []

    def recorrer(obj):
        if isinstance(obj, list):
            for o in obj:
                recorrer(o)
        elif isinstance(obj, dict):
            tipo = obj.get("@type")
            tipos = tipo if isinstance(tipo, list) else [tipo]
            if any(t in ("Hotel", "LodgingBusiness", "Hostel", "Resort") for t in tipos):
                ofertas = obj.get("offers") or {}
                if isinstance(ofertas, list):
                    ofertas = ofertas[0] if ofertas else {}
                precio = precio_cop(str(ofertas.get("lowPrice") or ofertas.get("price") or obj.get("priceRange") or ""))
                m = _ID_HOTEL.search(str(obj.get("url", "")))
                calif = (obj.get("aggregateRating") or {}).get("ratingValue")
                if m and obj.get("name") and precio:
                    registros.append({
                        "url": f"trivago:{m.group(1)}", "ciudad": codigo, "nombre": obj["name"],
                        "precio": str(precio), "rating": _rating(str(calif)) if calif else None, "fuente": fuente,
                    })
            for v in obj.values():
                recorrer(v)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            recorrer(json.loads(script.string or ""))
        except ValueError:
            continue
    return registros


def parsear(html: str, codigo: str, fuente: str = "trivago") -> list[dict]:
    """Extrae un registro por alojamiento. Sirve tanto para la página de destino descargada en vivo
    como para las páginas guardadas a mano. Prueba las 3 estrategias y une los resultados por id."""
    soup = BeautifulSoup(html, "html.parser")
    por_id: dict[str, dict] = {}

    # 1. Microdatos schema.org: <article itemtype="https://schema.org/Hotel">. En los resultados, las ofertas
    #    (precios) están en un panel HERMANO del <article>, dentro del mismo <li data-accommodation>:
    #    por eso la tarjeta es ese <li> cuando existe.
    for hotel in soup.select('[itemtype*="schema.org/Hotel"], [itemtype*="schema.org/LodgingBusiness"]'):
        tarjeta = hotel.find_parent(attrs={"data-accommodation": True}) or hotel
        if (r := _desde_tarjeta(tarjeta, codigo, fuente)):
            por_id.setdefault(r["url"], r)

    # 2. Enlaces /oar/...?search=100-<id>: la tarjeta es el contenedor más pequeño con precio
    for enlace in soup.select('a[href*="search=100-"]'):
        id_hotel = _ID_HOTEL.search(enlace["href"]).group(1)
        if f"trivago:{id_hotel}" in por_id:
            continue
        tarjeta = _tarjeta_del_enlace(enlace)
        if tarjeta is not None and (r := _desde_tarjeta(tarjeta, codigo, fuente, id_hotel)):
            por_id.setdefault(r["url"], r)

    # 3. JSON-LD
    for r in _json_ld(soup, codigo, fuente):
        por_id.setdefault(r["url"], r)

    return list(por_id.values())


def recortar(html: str) -> str:
    """Reduce una página guardada (~1 MB) a lo que usa el parser, para no guardar la página completa en el repo."""
    soup = BeautifulSoup(html, "html.parser")
    for basura in soup.select("script:not([type='application/ld+json']), style, svg, picture, noscript, iframe, link, meta:not([itemprop])"):
        basura.decompose()
    cuerpo = soup.body or soup
    return "<!-- Muestra recortada de una página de Trivago guardada desde el navegador -->\n" + str(cuerpo)


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 2 and sys.argv[1] == "--probar":
        # Prueba EN VIVO desde tu equipo (no toca la BD): python trivago.py --probar
        import httpx
        from protego import Protego

        UA = "WanderSync-academic-bot/0.1 (proyecto universitario)"
        cab = {"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"}
        reglas = Protego.parse(httpx.get(f"{BASE}/robots.txt", headers=cab, timeout=15).text)
        for codigo, ruta in DESTINOS.items():
            url = BASE + ruta
            if not reglas.can_fetch(url, UA):
                print(f"{codigo}: robots.txt NO permite {unquote(url)}")
                continue
            r = httpx.get(url, headers=cab, timeout=20, follow_redirects=True)
            if r.status_code != 200 or ANTI_BOT.search(r.text):
                print(f"{codigo}: Trivago respondió HTTP {r.status_code}{' con desafío anti-bot' if ANTI_BOT.search(r.text) else ''}. No se evade: el flow usará las muestras guardadas.")
                continue
            hoteles = parsear(r.text, codigo)
            print(f"{codigo}: {len(hoteles)} hoteles")
            for h in hoteles[:3]:
                print(f"     {h['nombre']} · ${int(h['precio']):,} · {h['rating']}".replace(",", "."))
            if not hoteles:
                # En muestras/ porque esa carpeta está montada como volumen: el archivo aparece en tu equipo
                with open(f"muestras/diagnostico-{codigo}.html", "w", encoding="utf-8") as f:
                    f.write(r.text)
                print(f"     0 hoteles: guardé el HTML en ingesta/muestras/diagnostico-{codigo}.html para revisar los selectores")
    elif len(sys.argv) == 3:
        # Recortar una página guardada: python trivago.py pagina.html muestras/trivago/MDE-medellin.html
        recortada = recortar(open(sys.argv[1], encoding="utf-8").read())
        open(sys.argv[2], "w", encoding="utf-8").write(recortada)
        print(f"{sys.argv[2]}: {len(parsear(recortada, 'XXX'))} alojamientos con precio")
    else:
        print("Uso: python trivago.py --probar  |  python trivago.py pagina.html muestras/trivago/MDE-medellin.html")
