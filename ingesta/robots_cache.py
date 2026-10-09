# robots.txt con caché en memoria de cada worker de Dask.
#
# Con 30 ciudades, leer el robots.txt en cada tarea serían 30 peticiones extra por ejecución al mismo sitio.
# Aquí se lee una vez por sitio y por franja de 30 minutos en cada worker (menos carga para el sitio).
#
# ¿Por qué en un módulo aparte y no en flow.py? flow.py se ejecuta como __main__, y Dask/cloudpickle envía sus
# funciones "por valor". Una función envuelta con @lru_cache no se puede enviar así: se envía "por nombre"
# (__main__._robots) y el scheduler y los workers no la encuentran ("Error during deserialization of the
# task graph"). Un módulo importable sí viaja por nombre: los workers lo importan desde /app (PYTHONPATH).
import time
from functools import lru_cache

import httpx
from protego import Protego


@lru_cache(maxsize=8)
def _leer(base: str, franja: int, user_agent: str) -> Protego:
    respuesta = httpx.get(f"{base}/robots.txt", headers={"User-Agent": user_agent}, timeout=15)
    return Protego.parse(respuesta.text)


def reglas(base: str, user_agent: str) -> Protego:
    """Reglas de robots.txt del sitio, cacheadas por 30 minutos (franja = hora actual // 1800 s)."""
    return _leer(base, int(time.time() // 1800), user_agent)
