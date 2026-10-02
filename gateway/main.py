# API GATEWAY GraphQL: la ÚNICA puerta de entrada del frontend al backend.
# El frontend nunca habla directo con Vuelos/Hoteles/Autos/Órdenes: todo pasa por aquí.
#
# ¿Por qué GraphQL elimina el over-fetching? En REST el SERVIDOR decide qué campos devuelve
# cada endpoint. En GraphQL el CLIENTE escribe exactamente los campos que quiere y recibe
# solo esos, en una sola petición (en vez de llamar a 3 endpoints REST y descartar datos).
import asyncio
import httpx
import strawberry
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

# Direcciones internas de los microservicios (nombres de servicio en docker-compose)
VUELOS = "http://vuelos:8000"
HOTELES = "http://hoteles:8000"
AUTOS = "http://autos:8000"
ORDENES = "http://ordenes:8000"


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
    precio_total: float


# Resultado de una reserva (el estado de la SAGA)
@strawberry.type
class Orden:
    saga_id: str
    estado: str                # CONFIRMADA | COMPENSADA | REQUIERE_ATENCION | EN_CURSO...
    paso: str | None = None    # "| None" = campo opcional (puede venir vacío)


# ---------------- QUERIES (lecturas) ----------------

@strawberry.type
class Query:

    @strawberry.field(description="Paquetes disponibles (vuelo + hotel + auto) hacia una ciudad destino")
    async def paquetes(self, destino: str, noches: int = 1) -> list[Paquete]:
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
                precio_total=v["precio"] + (h["precio_noche"] + a["precio_dia"]) * noches,
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
        return Orden(saga_id=d["saga_id"], estado=d["estado"], paso=d["paso"])


# ---------------- MUTATIONS (escrituras) ----------------

@strawberry.type
class Mutation:

    @strawberry.mutation(description="Reserva un paquete completo. Dispara la SAGA en el servicio de Órdenes")
    async def reservar_paquete(self, vuelo_id: int, hotel_id: int, auto_id: int) -> Orden:
        # timeout amplio: si hay que compensar con reintentos, la SAGA puede tardar varios segundos
        async with httpx.AsyncClient(timeout=60) as cliente:
            r = await cliente.post(
                f"{ORDENES}/ordenes",
                json={"vuelo_id": vuelo_id, "hotel_id": hotel_id, "auto_id": auto_id},
            )
        r.raise_for_status()
        d = r.json()
        return Orden(saga_id=d["saga_id"], estado=d["estado"])


# ---------------- Servidor ----------------

schema = strawberry.Schema(query=Query, mutation=Mutation)

app = FastAPI()
# Monta GraphQL en /graphql. Al abrir esa URL en el navegador aparece GraphiQL (el editor interactivo).
app.include_router(GraphQLRouter(schema), prefix="/graphql")


@app.get("/health")
def health():
    return {"status": "ok"}
