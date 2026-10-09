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
OFERTAS = "http://ofertas:8000"

# Reglas de capacidad del paquete: el vuelo se cobra por persona; el hotel, por habitación (hasta 2 personas
# cada una) y el auto, por vehículo (hasta 5 personas cada uno).
MAX_PERSONAS = 9
PERSONAS_POR_HABITACION = 2
PERSONAS_POR_AUTO = 5


def validar_personas(personas: int) -> None:
    if not 1 <= personas <= MAX_PERSONAS:
        raise ValueError(f"El número de personas debe estar entre 1 y {MAX_PERSONAS}")


def validar_noches(noches: int) -> None:
    if not 1 <= noches <= 30:
        raise ValueError("El número de noches debe estar entre 1 y 30")


def precio_total(v: dict, h: dict, a: dict | None, personas: int, noches: int) -> float:
    """vuelo x personas + (hotel x habitaciones + auto x autos) x noches. Se usa al listar los paquetes Y al
    reservar: el precio de la reserva lo calcula el servidor, nunca se acepta un precio enviado por el navegador."""
    habitaciones = math.ceil(personas / PERSONAS_POR_HABITACION)
    autos = math.ceil(personas / PERSONAS_POR_AUTO) if a else 0
    return v["precio"] * personas + (h["precio_noche"] * habitaciones + (a["precio_dia"] if a else 0) * autos) * noches


# ---------------- TIPOS del esquema GraphQL ----------------
# @strawberry.type convierte una clase Python en un tipo GraphQL.
# Strawberry pasa los nombres a camelCase automáticamente: precio_noche -> precioNoche.

@strawberry.type
class Vuelo:
    id: int
    origen: str
    destino: str
    precio: float
    fuente: str            # "semilla" | "booking-muestra" (vuelos desde Bogotá de la página de Booking)


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
    fuente: str            # "semilla" | "booking-muestra" (precio medio de alquiler por día en Booking)


# Un paquete = una combinación vuelo + hotel + auto en la misma ciudad destino
@strawberry.type
class Paquete:
    vuelo: Vuelo
    hotel: Hotel
    auto: Auto | None          # None en destinos sin alquiler de autos (San Andrés, Pereira): vuelo + hotel
    personas: int
    habitaciones: int          # ceil(personas / 2)
    autos: int                 # ceil(personas / 5), 0 si el paquete no trae auto
    precio_total: float        # vuelo x personas + (hotel x habitaciones + auto x autos) x noches


# Ciudad con paquetes (tiene vuelo y alojamiento)
@strawberry.type
class Destino:
    codigo: str                # IATA: MDE, CUN, PAR...
    nombre: str
    pais: str | None
    vuelo_desde: float         # vuelo más barato desde Bogotá, por persona


# Oferta de un proveedor externo (Booking.com) para un destino
@strawberry.type
class Oferta:
    categoria: str             # alojamiento | vuelos | coches | atracciones
    destino: str
    titulo: str | None         # "Bogotá → Medellín", nombre de la atracción...
    detalle: str | None        # país del vuelo, puntos de alquiler de coches...
    ciudad: str | None         # código (MDE, CLO, MAD...) si el destino es una ciudad de WanderSync
    cantidad: int | None       # cuántas ofertas tiene el proveedor en ese destino
    precio_desde: float
    unidad: str | None         # "por noche", "al día", "por persona"...
    campana: str | None
    url: str | None
    fuente: str


# Una reserva (el estado de su SAGA + el resumen de lo reservado)
@strawberry.type
class Orden:
    saga_id: str
    estado: str                # EN_CURSO | CONFIRMADA | COMPENSADA | CANCELANDO | CANCELADA | REQUIERE_ATENCION
    paso: str | None = None    # "| None" = campo opcional (puede venir vacío)
    personas: int | None = None
    noches: int | None = None
    destino: str | None = None
    vuelo: str | None = None   # "BOG → MDE"
    hotel: str | None = None
    auto: str | None = None
    total: float | None = None
    creado: str | None = None  # fecha ISO 8601


def orden_de(d: dict) -> Orden:
    """Respuesta JSON del servicio Órdenes -> tipo GraphQL (solo los campos del esquema)."""
    campos = {k: d.get(k) for k in Orden.__annotations__}
    campos["saga_id"] = str(d["saga_id"])
    campos["total"] = float(d["total"]) if d.get("total") is not None else None
    return Orden(**campos)


async def exigir_sesion(info: strawberry.Info) -> int:
    u = await seguridad.usuario_actual(info)
    if u is None:
        raise PermissionError("Debes iniciar sesión")
    return u[0]


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
        validar_noches(noches)
        habitaciones = math.ceil(personas / PERSONAS_POR_HABITACION)
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
        # Si la ciudad no tiene alquiler de autos, el paquete es vuelo + hotel ([None] = una sola "opción" sin auto).
        autos_ciudad = ra.json() or [None]
        return [
            Paquete(
                vuelo=Vuelo(**v),
                hotel=Hotel(**h),
                auto=Auto(**a) if a else None,
                personas=personas,
                habitaciones=habitaciones,
                autos=math.ceil(personas / PERSONAS_POR_AUTO) if a else 0,
                precio_total=precio_total(v, h, a, personas, noches),
            )
            for v in rv.json()
            for h in rh.json()
            for a in autos_ciudad
        ]

    @strawberry.field(description="Ciudades con paquetes: tienen vuelo Y alojamiento")
    async def destinos(self) -> list[Destino]:
        async with httpx.AsyncClient(timeout=5) as cliente:
            rv, rh = await asyncio.gather(cliente.get(f"{VUELOS}/destinos"), cliente.get(f"{HOTELES}/ciudades"))
        rv.raise_for_status()
        rh.raise_for_status()
        con_hotel = set(rh.json())
        return sorted(
            (
                Destino(codigo=d["codigo"], nombre=d["nombre"] or d["codigo"], pais=d["pais"], vuelo_desde=d["vuelo_desde"])
                for d in rv.json()
                if d["codigo"] in con_hotel
            ),
            key=lambda d: d.nombre,
        )

    @strawberry.field(description="Ofertas de Booking por categoría: alojamiento, vuelos, coches, atracciones")
    async def ofertas(self, categoria: str | None = None) -> list[Oferta]:
        async with httpx.AsyncClient(timeout=5) as cliente:
            r = await cliente.get(f"{OFERTAS}/ofertas", params={"categoria": categoria} if categoria else None)
        if r.status_code == 422:
            raise ValueError(r.json()["detail"])
        r.raise_for_status()
        campos = Oferta.__annotations__.keys()
        return [Oferta(**{k: o[k] for k in campos}) for o in r.json()]

    @strawberry.field(description="Consulta el estado de una reserva propia (SAGA) por su id (requiere sesión)")
    async def orden(self, info: strawberry.Info, saga_id: str) -> Orden | None:
        usuario_id = await exigir_sesion(info)
        async with httpx.AsyncClient(timeout=5) as cliente:
            # usuario_id viaja siempre: la reserva de otra persona responde 404, igual que una que no existe
            r = await cliente.get(f"{ORDENES}/ordenes/{saga_id}", params={"usuario_id": usuario_id})
        if r.status_code in (404, 422):   # 422 = el id no es un UUID válido
            return None
        r.raise_for_status()
        return orden_de(r.json())

    @strawberry.field(description="Reservas del usuario de la sesión, la más reciente primero (requiere sesión)")
    async def mis_reservas(self, info: strawberry.Info) -> list[Orden]:
        usuario_id = await exigir_sesion(info)
        async with httpx.AsyncClient(timeout=5) as cliente:
            r = await cliente.get(f"{ORDENES}/ordenes", params={"usuario_id": usuario_id})
        r.raise_for_status()
        return [orden_de(d) for d in r.json()]

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

    @strawberry.mutation(description="Reserva un paquete (requiere sesión). Dispara la SAGA en Órdenes")
    async def reservar_paquete(
        self,
        info: strawberry.Info,
        vuelo_id: int,
        hotel_id: int,
        auto_id: int | None = None,
        personas: int = 1,
        noches: int = 1,
    ) -> Orden:
        # Checkout: ruta sensible -> rate limit + autenticación obligatoria
        seguridad.limitar(info, "10/minute", "checkout", seguridad.ip_cliente(info))
        validar_personas(personas)
        validar_noches(noches)
        usuario_id = await exigir_sesion(info)

        # El Gateway consulta cada pieza por su id (en paralelo) para validar el paquete y calcular el precio
        # en el servidor: el navegador solo manda ids, nunca precios.
        async with httpx.AsyncClient(timeout=5) as cliente:
            pedidos = [cliente.get(f"{VUELOS}/vuelos/{vuelo_id}"), cliente.get(f"{HOTELES}/hoteles/{hotel_id}")]
            if auto_id is not None:
                pedidos.append(cliente.get(f"{AUTOS}/autos/{auto_id}"))
            respuestas = await asyncio.gather(*pedidos)
        if any(r.status_code == 404 for r in respuestas):
            raise ValueError("Ese paquete ya no está disponible; vuelve a buscar")
        for r in respuestas:
            r.raise_for_status()
        v, h = respuestas[0].json(), respuestas[1].json()
        a = respuestas[2].json() if auto_id is not None else None
        # Vuelo, hotel y auto tienen que ser de la misma ciudad (nadie arma un paquete "Cali + hotel en Madrid")
        if h["ciudad"] != v["destino"] or (a and a["ciudad"] != v["destino"]):
            raise ValueError("El vuelo, el hotel y el auto deben ser del mismo destino")

        # timeout amplio: si hay que compensar con reintentos, la SAGA puede tardar varios segundos
        async with httpx.AsyncClient(timeout=60) as cliente:
            r = await cliente.post(
                f"{ORDENES}/ordenes",
                json={
                    "usuario_id": usuario_id, "vuelo_id": vuelo_id, "hotel_id": hotel_id, "auto_id": auto_id,
                    "personas": personas, "noches": noches, "destino": v["destino"],
                    "vuelo": f"{v['origen']} → {v['destino']}", "hotel": h["nombre"],
                    "auto": a["modelo"] if a else None, "total": precio_total(v, h, a, personas, noches),
                },
            )
        r.raise_for_status()
        d = r.json()
        return Orden(saga_id=str(d["saga_id"]), estado=d["estado"], personas=personas, noches=noches)

    @strawberry.mutation(description="Cancela una reserva propia confirmada (requiere sesión). Compensa con la SAGA")
    async def cancelar_reserva(self, info: strawberry.Info, saga_id: str) -> Orden:
        seguridad.limitar(info, "10/minute", "cancelar", seguridad.ip_cliente(info))
        usuario_id = await exigir_sesion(info)
        async with httpx.AsyncClient(timeout=60) as cliente:
            r = await cliente.post(f"{ORDENES}/ordenes/{saga_id}/cancelar", json={"usuario_id": usuario_id})
        if r.status_code in (404, 422):
            raise ValueError("Reserva no encontrada")
        if r.status_code == 409:
            raise ValueError(r.json()["detail"])
        r.raise_for_status()
        return orden_de(r.json())


# ---------------- Servidor ----------------

schema = strawberry.Schema(query=Query, mutation=Mutation)

app = FastAPI()
# Monta GraphQL en /graphql. Al abrir esa URL en el navegador aparece GraphiQL (el editor interactivo).
app.include_router(GraphQLRouter(schema), prefix="/graphql")


@app.get("/health")
def health():
    return {"status": "ok"}
