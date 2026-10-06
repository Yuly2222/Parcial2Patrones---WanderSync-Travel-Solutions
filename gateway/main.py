# API GATEWAY GraphQL: la ÚNICA puerta de entrada del frontend al backend.
# El frontend nunca habla directo con Vuelos/Hoteles/Autos/Órdenes: todo pasa por aquí.
#
# ¿Por qué GraphQL elimina el over-fetching? En REST el SERVIDOR decide qué campos devuelve
# cada endpoint. En GraphQL el CLIENTE escribe exactamente los campos que quiere y recibe
# solo esos, en una sola petición (en vez de llamar a 3 endpoints REST y descartar datos).
import asyncio
import math
import httpx
import psycopg
import strawberry
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

import seguridad   # Argon2id, sesiones (Session Fixation) y Rate Limiting -> ver seguridad.py

# Direcciones internas de los microservicios (nombres de servicio en docker-compose)
VUELOS = "http://vuelos:8000"
HOTELES = "http://hoteles:8000"
AUTOS = "http://autos:8000"
ORDENES = "http://ordenes:8000"

# Reglas de capacidad del paquete: el vuelo se cobra por persona; el hotel, por habitación (hasta 2 personas
# cada una) y el auto, por vehículo (hasta 5 personas cada uno).
MAX_PERSONAS = 9
PERSONAS_POR_HABITACION = 2
PERSONAS_POR_AUTO = 5


def validar_personas(personas: int) -> None:
    if not 1 <= personas <= MAX_PERSONAS:
        raise ValueError(f"El número de personas debe estar entre 1 y {MAX_PERSONAS}")


# ---------------- TIPOS del esquema GraphQL ----------------
# @strawberry.type convierte una clase Python en un tipo GraphQL.
# Strawberry pasa los nombres a camelCase automáticamente: precio_noche -> precioNoche.

@strawberry.type
class Vuelo:
    id: int
    origen: str
    destino: str
    precio: float


@strawberry.type
class Hotel:
    id: int
    nombre: str
    ciudad: str
    precio_noche: float
    rating: float | None   # calificación 0-10 (los hoteles semilla no tienen)
    fuente: str            # "semilla" | "hostelworld" | "trivago" (scraping en vivo) | "trivago-muestra" (respaldo guardado)


@strawberry.type
class Auto:
    id: int
    modelo: str
    ciudad: str
    precio_dia: float


# Un paquete = una combinación vuelo + hotel + auto en la misma ciudad destino
@strawberry.type
class Paquete:
    vuelo: Vuelo
    hotel: Hotel
    auto: Auto
    personas: int
    habitaciones: int          # ceil(personas / 2)
    autos: int                 # ceil(personas / 5)
    precio_total: float        # vuelo x personas + (hotel x habitaciones + auto x autos) x noches


# Resultado de una reserva (el estado de la SAGA)
@strawberry.type
class Orden:
    saga_id: str
    estado: str                # CONFIRMADA | COMPENSADA | REQUIERE_ATENCION | EN_CURSO...
    paso: str | None = None    # "| None" = campo opcional (puede venir vacío)
    personas: int | None = None


# Usuario autenticado (nunca se expone el hash de la contraseña)
@strawberry.type
class Usuario:
    id: int
    email: str


# ---------------- QUERIES (lecturas) ----------------

@strawberry.type
class Query:

    @strawberry.field(description="Paquetes disponibles (vuelo + hotel + auto) hacia una ciudad destino")
    async def paquetes(self, destino: str, noches: int = 1, personas: int = 1) -> list[Paquete]:
        validar_personas(personas)
        if not 1 <= noches <= 30:
            raise ValueError("El número de noches debe estar entre 1 y 30")
        habitaciones = math.ceil(personas / PERSONAS_POR_HABITACION)
        autos = math.ceil(personas / PERSONAS_POR_AUTO)
        async with httpx.AsyncClient(timeout=5) as cliente:
            # asyncio.gather lanza las 3 peticiones EN PARALELO (no una tras otra):
            # la respuesta tarda lo que el servicio más lento, no la suma de los tres.
            # Cada servicio filtra en su propia BD por ciudad -> solo viajan los datos necesarios.
            rv, rh, ra = await asyncio.gather(
                cliente.get(f"{VUELOS}/vuelos", params={"destino": destino}),
                cliente.get(f"{HOTELES}/hoteles", params={"ciudad": destino}),
                cliente.get(f"{AUTOS}/autos", params={"ciudad": destino}),
            )
        for r in (rv, rh, ra):
            r.raise_for_status()  # si un servicio falla, GraphQL devuelve el error en el campo "errors"

        # Combina cada vuelo con cada hotel y cada auto de esa ciudad.
        # Vuelo(**v) crea el objeto a partir del diccionario JSON (las llaves coinciden con los campos).
        return [
            Paquete(
                vuelo=Vuelo(**v),
                hotel=Hotel(**h),
                auto=Auto(**a),
                personas=personas,
                habitaciones=habitaciones,
                autos=autos,
                precio_total=v["precio"] * personas
                + (h["precio_noche"] * habitaciones + a["precio_dia"] * autos) * noches,
            )
            for v in rv.json()
            for h in rh.json()
            for a in ra.json()
        ]

    @strawberry.field(description="Consulta el estado de una reserva (SAGA) por su id")
    async def orden(self, saga_id: str) -> Orden | None:
        async with httpx.AsyncClient(timeout=5) as cliente:
            r = await cliente.get(f"{ORDENES}/ordenes/{saga_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        d = r.json()
        return Orden(saga_id=d["saga_id"], estado=d["estado"], paso=d["paso"], personas=d.get("personas"))

    @strawberry.field(description="Usuario de la sesión actual (null si no hay sesión)")
    async def yo(self, info: strawberry.Info) -> Usuario | None:
        u = await seguridad.usuario_actual(info)
        return Usuario(id=u[0], email=u[1]) if u else None


# ---------------- MUTATIONS (escrituras) ----------------

@strawberry.type
class Mutation:

    @strawberry.mutation(description="Crea una cuenta. Contraseña de 10 a 128 caracteres")
    async def registrar(self, info: strawberry.Info, email: str, password: str) -> Usuario:
        seguridad.limitar(info, "3/minute", "registro", seguridad.ip_cliente(info))
        email = email.strip().lower()
        if "@" not in email or len(email) > 254:
            raise ValueError("Email inválido")
        # Máximo 128: sin tope, alguien podría mandar contraseñas de megas y saturar la CPU con Argon2
        if not 10 <= len(password) <= 128:
            raise ValueError("La contraseña debe tener entre 10 y 128 caracteres")
        password_hash = await seguridad.hashear_password(password)
        async with await psycopg.AsyncConnection.connect(seguridad.DB) as conn:
            cur = await conn.execute(
                "INSERT INTO usuarios (email, password_hash) VALUES (%s, %s) "
                "ON CONFLICT (email) DO NOTHING RETURNING id",
                (email, password_hash),
            )
            fila = await cur.fetchone()
        if fila is None:
            raise ValueError("No se pudo registrar con ese email")
        return Usuario(id=fila[0], email=email)

    @strawberry.mutation(description="Inicia sesión. Emite una cookie de sesión NUEVA (anti Session Fixation)")
    async def iniciar_sesion(self, info: strawberry.Info, email: str, password: str) -> Usuario:
        email = email.strip().lower()
        # Dos límites contra fuerza bruta: por IP (un atacante, muchas cuentas)
        # y por email (muchas IPs atacando la misma cuenta)
        seguridad.limitar(info, "5/minute", "login-ip", seguridad.ip_cliente(info))
        seguridad.limitar(info, "10/15minutes", "login-email", email)
        async with await psycopg.AsyncConnection.connect(seguridad.DB) as conn:
            cur = await conn.execute("SELECT id, password_hash FROM usuarios WHERE email = %s", (email,))
            fila = await cur.fetchone()
        # Se verifica SIEMPRE (aunque el email no exista) para que el tiempo de respuesta no revele nada
        if not await seguridad.verificar_password(fila[1] if fila else None, password):
            raise ValueError("Credenciales inválidas")   # mensaje genérico: no dice si falló el email o la clave
        await seguridad.crear_sesion(info, fila[0])
        return Usuario(id=fila[0], email=email)

    @strawberry.mutation(description="Cierra la sesión actual")
    async def cerrar_sesion(self, info: strawberry.Info) -> bool:
        await seguridad.cerrar_sesion(info)
        return True

    @strawberry.mutation(description="Reserva un paquete completo (requiere sesión). Dispara la SAGA en Órdenes")
    async def reservar_paquete(
        self, info: strawberry.Info, vuelo_id: int, hotel_id: int, auto_id: int, personas: int = 1
    ) -> Orden:
        # Checkout: ruta sensible -> rate limit + autenticación obligatoria
        seguridad.limitar(info, "10/minute", "checkout", seguridad.ip_cliente(info))
        validar_personas(personas)
        if await seguridad.usuario_actual(info) is None:
            raise PermissionError("Debes iniciar sesión para reservar")
        # timeout amplio: si hay que compensar con reintentos, la SAGA puede tardar varios segundos
        async with httpx.AsyncClient(timeout=60) as cliente:
            r = await cliente.post(
                f"{ORDENES}/ordenes",
                json={"vuelo_id": vuelo_id, "hotel_id": hotel_id, "auto_id": auto_id, "personas": personas},
            )
        r.raise_for_status()
        d = r.json()
        return Orden(saga_id=d["saga_id"], estado=d["estado"], personas=personas)


# ---------------- Servidor ----------------

schema = strawberry.Schema(query=Query, mutation=Mutation)

app = FastAPI()
# Monta GraphQL en /graphql. Al abrir esa URL en el navegador aparece GraphiQL (el editor interactivo).
app.include_router(GraphQLRouter(schema), prefix="/graphql")


@app.get("/health")
def health():
    return {"status": "ok"}
