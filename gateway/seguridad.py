# SEGURIDAD POR DISEÑO del API Gateway:
#   1. Contraseñas con Argon2id (hashing lento a propósito, con sal y alto costo de memoria).
#   2. Sesiones del lado del servidor con mitigación de Session Fixation (ID nuevo en cada login).
#   3. Rate Limiting en rutas sensibles (login, registro, checkout de reservas).
# Se centraliza en el Gateway porque es la ÚNICA puerta de entrada: lo que no pase por aquí no entra.
import asyncio
import hashlib
import os
import secrets
import socket
import time

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

DB = os.environ["DATABASE_URL"]   # base de datos "auth"


# ======================= 1. CONTRASEÑAS: Argon2id =======================
# Argon2id ganó la Password Hashing Competition y es el algoritmo recomendado por OWASP.
# Es LENTO y consume MEMORIA a propósito: probar millones de contraseñas (fuerza bruta offline,
# si roban la BD) se vuelve carísimo, sobre todo en GPUs, que tienen poca memoria por núcleo.
#   time_cost=3       -> 3 pasadas sobre la memoria
#   memory_cost=65536 -> 64 MiB de RAM por cada hash
#   parallelism=4     -> 4 hilos
# PasswordHasher usa el tipo Argon2id por defecto y genera una SAL aleatoria por contraseña
# (dos usuarios con la misma contraseña tienen hashes distintos).
ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)

# Hash de relleno: si el email no existe, igual se verifica contra este hash, para que la respuesta
# tarde lo mismo que con un email real. Así un atacante no descubre qué emails existen midiendo tiempos.
_HASH_FALSO = ph.hash(secrets.token_urlsafe(16))


async def hashear_password(password: str) -> str:
    # asyncio.to_thread: Argon2 tarda ~100 ms de CPU; en un hilo aparte no bloquea al resto de peticiones
    return await asyncio.to_thread(ph.hash, password)


async def verificar_password(hash_guardado: str | None, password: str) -> bool:
    try:
        await asyncio.to_thread(ph.verify, hash_guardado or _HASH_FALSO, password)
        return hash_guardado is not None
    except (VerificationError, InvalidHashError):
        return False


# ======================= 2. SESIONES + SESSION FIXATION =======================
# Session Fixation: el atacante consigue que la víctima use un ID de sesión que él ya conoce
# (por ejemplo, plantándole una cookie). Si al iniciar sesión el servidor REUTILIZA ese ID,
# el atacante queda autenticado como la víctima.
# Mitigación: en CADA login exitoso se DESTRUYE la sesión que traía el navegador y se emite
# un ID NUEVO, aleatorio e impredecible. El ID que conocía el atacante deja de servir.
COOKIE = "session"
DURACION_SEG = 3600   # 1 hora
# Secure=True obliga a enviar la cookie solo por HTTPS. En local (http://localhost) debe ser false;
# en producción, con HTTPS, se pone COOKIE_SECURE=true.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"


def _https(request) -> bool:
    """¿La cookie debe ser Secure? Sí si se configuró así, o si la petición llegó por HTTPS a través del
    proxy de confianza (la URL pública del túnel es https aunque nginx y el Gateway hablen http por dentro)."""
    if COOKIE_SECURE:
        return True
    return request.headers.get("x-forwarded-proto") == "https" and ip_confiable(request)


def _sha256(token: str) -> str:
    # En la BD se guarda el hash del token, no el token: si roban la BD, no pueden usar las sesiones
    return hashlib.sha256(token.encode()).hexdigest()


async def crear_sesion(info, usuario_id: int) -> None:
    request, response = info.context["request"], info.context["response"]
    token_anterior = request.cookies.get(COOKIE)
    token_nuevo = secrets.token_urlsafe(32)   # 256 bits aleatorios criptográficamente seguros

    async with await psycopg.AsyncConnection.connect(DB) as conn:
        if token_anterior:
            # Se invalida el ID que venía del navegador (posiblemente fijado por un atacante)
            await conn.execute("DELETE FROM sesiones WHERE id = %s", (_sha256(token_anterior),))
        await conn.execute(
            "INSERT INTO sesiones (id, usuario_id, expira) VALUES (%s, %s, now() + make_interval(secs => %s))",
            (_sha256(token_nuevo), usuario_id, DURACION_SEG),
        )

    response.set_cookie(
        COOKIE,
        token_nuevo,
        max_age=DURACION_SEG,
        httponly=True,       # JavaScript no puede leerla -> un XSS no puede robar la sesión
        samesite="strict",   # no se envía desde otros sitios -> protege contra CSRF
        secure=_https(request),
    )


async def usuario_actual(info) -> tuple[int, str] | None:
    """Devuelve (id, email) del usuario de la sesión, o None si no hay sesión válida."""
    token = info.context["request"].cookies.get(COOKIE)
    if not token:
        return None
    async with await psycopg.AsyncConnection.connect(DB) as conn:
        cur = await conn.execute(
            "SELECT u.id, u.email FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id "
            "WHERE s.id = %s AND s.expira > now()",   # las sesiones vencidas no sirven
            (_sha256(token),),
        )
        return await cur.fetchone()


async def cerrar_sesion(info) -> None:
    token = info.context["request"].cookies.get(COOKIE)
    if token:
        async with await psycopg.AsyncConnection.connect(DB) as conn:
            await conn.execute("DELETE FROM sesiones WHERE id = %s", (_sha256(token),))
    info.context["response"].delete_cookie(COOKIE)


# ======================= 3. RATE LIMITING =======================
# Limita cuántas veces se puede llamar una operación sensible en una ventana de tiempo.
# Frena la fuerza bruta de contraseñas y el abuso/DoS del checkout.
# "Moving window" = ventana deslizante: cuenta las llamadas de los últimos N segundos exactos
# (no se puede "hacer trampa" concentrando intentos justo en el cambio de minuto).
#
# Como todo pasa por un único endpoint /graphql, el límite se aplica POR OPERACIÓN dentro de
# cada resolver (un limitador por URL no distinguiría un login de una consulta de paquetes).
# ponytail: contador en memoria = vale para UNA réplica del Gateway; con varias réplicas,
# cambiar MemoryStorage() por RedisStorage("redis://...") para que compartan el contador.
_limitador = MovingWindowRateLimiter(MemoryStorage())


class LimiteExcedido(Exception):
    pass


# El frontend (nginx) reenvía /graphql al Gateway. Para el Gateway, esas peticiones vienen de la IP
# de nginx: si contáramos por esa IP, TODOS los usuarios compartirían un mismo límite (y uno solo
# podría bloquear a los demás). nginx envía la IP real en la cabecera X-Real-IP.
# PERO esa cabecera la puede escribir cualquiera: solo se le cree si la petición viene del proxy
# de confianza (el contenedor "frontend"). Una petición directa a :8000 con X-Real-IP falsa se ignora.
PROXY_CONFIABLE = os.environ.get("PROXY_CONFIABLE", "")   # nombre del servicio en docker-compose
_cache_proxy: tuple[float, set[str]] = (0.0, set())


def _ips_proxy() -> set[str]:
    """IPs actuales del proxy de confianza (DNS interno de Docker), cacheadas 30 s."""
    global _cache_proxy
    ahora = time.monotonic()
    if ahora - _cache_proxy[0] > 30:
        try:
            ips = {a[4][0] for a in socket.getaddrinfo(PROXY_CONFIABLE, None)}
        except OSError:   # el contenedor frontend aún no existe o no se configuró
            ips = set()
        _cache_proxy = (ahora, ips)
    return _cache_proxy[1]


def ip_confiable(request) -> bool:
    """¿La petición viene del proxy de confianza (el contenedor frontend)?"""
    return bool(PROXY_CONFIABLE) and request.client.host in _ips_proxy()


def ip_cliente(info) -> str:
    request = info.context["request"]
    if ip_confiable(request):
        return request.headers.get("x-real-ip", request.client.host)
    return request.client.host


def limitar(info, regla: str, *claves: str) -> None:
    """regla: ej. "5/minute". claves: identifican qué se cuenta (ej. "login", ip)."""
    if not _limitador.hit(parse(regla), *claves):
        info.context["response"].status_code = 429   # HTTP 429 Too Many Requests
        raise LimiteExcedido("Demasiados intentos. Espera un momento e inténtalo de nuevo.")
