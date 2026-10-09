# Microservicio de Órdenes = ORQUESTADOR de la SAGA.
# Es el "director": llama en orden a Vuelos -> Hoteles -> Autos y, si alguno falla,
# ejecuta las compensaciones en orden inverso. Toda la lógica de la SAGA vive SOLO aquí.
import os
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
import httpx                    # Cliente HTTP para llamar a los otros microservicios
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB = os.environ["DATABASE_URL"]  # apunta a la base de datos "ordenes" (tabla sagas)

# Migración idempotente al arrancar (db/init.sql solo corre al crear el volumen por primera vez).
# Cada SAGA queda ligada a su usuario (para "Mis reservas") y guarda un resumen de lo reservado:
# Órdenes no puede consultar las BD de los otros servicios (database per service), así que el Gateway
# le manda ese resumen al crear la orden.
MIGRACION = """
ALTER TABLE sagas ALTER COLUMN auto_id DROP NOT NULL;            -- destinos sin alquiler de autos
ALTER TABLE sagas ADD COLUMN IF NOT EXISTS usuario_id INT;
ALTER TABLE sagas ADD COLUMN IF NOT EXISTS noches     INT;
ALTER TABLE sagas ADD COLUMN IF NOT EXISTS destino    TEXT;
ALTER TABLE sagas ADD COLUMN IF NOT EXISTS vuelo      TEXT;
ALTER TABLE sagas ADD COLUMN IF NOT EXISTS hotel      TEXT;
ALTER TABLE sagas ADD COLUMN IF NOT EXISTS auto       TEXT;
ALTER TABLE sagas ADD COLUMN IF NOT EXISTS total      NUMERIC(14, 2);
ALTER TABLE sagas ADD COLUMN IF NOT EXISTS creado     TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS sagas_usuario ON sagas (usuario_id, creado DESC);
"""


@asynccontextmanager
async def ciclo_de_vida(app):
    with psycopg.connect(DB) as conn:
        conn.execute(MIGRACION)
    yield


app = FastAPI(lifespan=ciclo_de_vida)


class Orden(BaseModel):
    usuario_id: int
    vuelo_id: int
    hotel_id: int
    auto_id: int | None = None                     # None = destino sin alquiler de autos (paquete vuelo + hotel)
    personas: int = Field(default=1, ge=1, le=9)   # Field valida el rango: fuera de 1-9 FastAPI responde 422
    noches: int = Field(default=1, ge=1, le=30)
    # Resumen para "Mis reservas" (lo arma el Gateway con los datos de cada servicio y el precio calculado allí)
    destino: str
    vuelo: str
    hotel: str
    auto: str | None = None
    total: Decimal


# Columnas que se devuelven al consultar una orden (mismo orden en el SELECT y en el diccionario)
CAMPOS = ("estado", "paso", "actualizado", "personas", "noches", "destino", "vuelo", "hotel", "auto", "total", "creado")
SELECT = f"SELECT id, {', '.join(CAMPOS)} FROM sagas"


def a_dict(fila):
    return {"saga_id": fila[0], **dict(zip(CAMPOS, fila[1:]))}


def guardar_estado(saga_id, estado, paso):
    """Registra en la tabla sagas en qué va la SAGA. Se llama en CADA paso:
    si el orquestador se cae, queda constancia de dónde iba (y es la evidencia para la demo)."""
    with psycopg.connect(DB) as conn:
        conn.execute(
            "UPDATE sagas SET estado = %s, paso = %s, actualizado = now() WHERE id = %s",
            (estado, paso, saga_id),
        )
    # flush=True para que el mensaje salga de inmediato en "docker compose logs ordenes"
    print(f"[SAGA {saga_id}] {estado}: {paso}", flush=True)


def compensar(servicio, saga_id, intentos=5):
    """Llama a la compensación (cancelar) de un servicio. Una compensación NO puede rendirse:
    se reintenta con backoff exponencial (1s, 2s, 4s, 8s, 16s). Reintentar es seguro porque
    cancelar es idempotente. Devuelve True si logró cancelar, False si agotó los intentos."""
    url = f"http://{servicio}:8000/reservas/{saga_id}/cancelar"
    for i in range(intentos):
        try:
            httpx.post(url, timeout=5).raise_for_status()  # raise_for_status: lanza error si la respuesta es 4xx/5xx
            print(f"[SAGA {saga_id}] compensado: {servicio}", flush=True)
            return True
        except httpx.HTTPError as e:
            print(f"[SAGA {saga_id}] reintento {i + 1} cancelando {servicio}: {e}", flush=True)
            time.sleep(2 ** i)
    return False


@app.post("/ordenes")
def crear_orden(orden: Orden):
    saga_id = uuid.uuid4()  # identificador único de esta SAGA; viaja a todos los servicios (llave de idempotencia)

    # 1) Registrar la SAGA antes de empezar
    with psycopg.connect(DB) as conn:
        conn.execute(
            "INSERT INTO sagas (id, usuario_id, vuelo_id, hotel_id, auto_id, personas, noches, "
            "destino, vuelo, hotel, auto, total, estado, paso) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'EN_CURSO', 'inicio')",
            (saga_id, orden.usuario_id, orden.vuelo_id, orden.hotel_id, orden.auto_id, orden.personas,
             orden.noches, orden.destino, orden.vuelo, orden.hotel, orden.auto, orden.total),
        )

    # 2) Los pasos de la SAGA, EN ORDEN: (servicio, datos que necesita para reservar)
    pasos = [
        ("vuelos",  {"vuelo_id": orden.vuelo_id}),
        ("hoteles", {"hotel_id": orden.hotel_id}),
    ]
    if orden.auto_id is not None:   # paquete con auto (en San Andrés o Pereira no hay alquiler)
        pasos.append(("autos", {"auto_id": orden.auto_id}))

    intentados = []  # pila de servicios a los que ya les pedimos reservar
    for servicio, datos in pasos:
        # Se apila ANTES de llamar. Si la llamada da timeout no sabemos si alcanzó a reservar o no
        # ("falló" y "funcionó pero no me enteré" se ven igual). Como cancelar es idempotente,
        # cancelar algo que nunca se reservó es inofensivo: preferimos compensar de más que dejar huérfanos.
        intentados.append(servicio)
        guardar_estado(saga_id, "EN_CURSO", f"reservando {servicio}")
        try:
            httpx.post(
                f"http://{servicio}:8000/reservas",   # "vuelos", "hoteles"... son nombres de servicio en Compose
                json={"saga_id": str(saga_id), **datos},
                timeout=5,
            ).raise_for_status()
        except httpx.HTTPError as e:
            # 3) FALLO -> compensar en ORDEN INVERSO todo lo que se intentó
            guardar_estado(saga_id, "COMPENSANDO", f"falló {servicio}: {e}")
            sin_compensar = []
            for s in reversed(intentados):
                if not compensar(s, saga_id):
                    sin_compensar.append(s)
            if sin_compensar:
                # Ni con reintentos se pudo cancelar: nunca rendirse en silencio, queda marcado para un humano
                estado = "REQUIERE_ATENCION"
                # Se conserva qué paso falló: el frontend lo usa para dibujar la línea de tiempo
                guardar_estado(saga_id, estado, f"falló {servicio}; no se pudo cancelar: {sin_compensar}")
            else:
                estado = "COMPENSADA"
                guardar_estado(saga_id, estado, f"falló {servicio}; reservas previas canceladas")
            return {"saga_id": saga_id, "estado": estado}

    # 4) Happy path: todos los pasos salieron bien
    guardar_estado(saga_id, "CONFIRMADA", "vuelo, hotel y auto reservados" if orden.auto_id else "vuelo y hotel reservados")
    return {"saga_id": saga_id, "estado": "CONFIRMADA"}


# Reservas de un usuario, la más reciente primero ("Mis reservas")
@app.get("/ordenes")
def listar_ordenes(usuario_id: int):
    with psycopg.connect(DB) as conn:
        filas = conn.execute(f"{SELECT} WHERE usuario_id = %s ORDER BY creado DESC LIMIT 50", (usuario_id,)).fetchall()
    return [a_dict(f) for f in filas]


# Consultar cómo va / cómo terminó una SAGA.
# usuario_id: el Gateway lo manda siempre, así nadie puede ver la reserva de otra persona adivinando su id
# (para quien no es el dueño, la reserva "no existe": 404, sin revelar que sí existe).
@app.get("/ordenes/{saga_id}")
def ver_orden(saga_id: uuid.UUID, usuario_id: int | None = None):
    with psycopg.connect(DB) as conn:
        fila = conn.execute(
            f"{SELECT} WHERE id = %s AND (%s::int IS NULL OR usuario_id = %s)", (saga_id, usuario_id, usuario_id)
        ).fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return a_dict(fila)


class Cancelacion(BaseModel):
    usuario_id: int


# CANCELAR una reserva confirmada: es la misma lógica de compensación de la SAGA, pedida por el cliente.
# Se cancela en orden inverso (auto -> hotel -> vuelo) y cada cancelación es idempotente y con reintentos.
@app.post("/ordenes/{saga_id}/cancelar")
def cancelar_orden(saga_id: uuid.UUID, c: Cancelacion):
    with psycopg.connect(DB) as conn:
        # Transición ATÓMICA CONFIRMADA -> CANCELANDO: si llegan dos cancelaciones a la vez (doble clic, dos
        # pestañas), solo una encuentra la fila en CONFIRMADA; la otra recibe 409. Nada se cancela dos veces.
        fila = conn.execute(
            "UPDATE sagas SET estado = 'CANCELANDO', paso = 'cancelación pedida por el cliente', actualizado = now() "
            "WHERE id = %s AND usuario_id = %s AND estado = 'CONFIRMADA' RETURNING auto_id",
            (saga_id, c.usuario_id),
        ).fetchone()
        if fila is None:
            actual = conn.execute(
                "SELECT estado FROM sagas WHERE id = %s AND usuario_id = %s", (saga_id, c.usuario_id)
            ).fetchone()
    if fila is None:
        if actual is None:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        raise HTTPException(status_code=409, detail=f"Solo se puede cancelar una reserva confirmada (estado: {actual[0]})")
    print(f"[SAGA {saga_id}] CANCELANDO: pedido del cliente", flush=True)

    servicios = ["autos", "hoteles", "vuelos"] if fila[0] is not None else ["hoteles", "vuelos"]
    sin_cancelar = [s for s in servicios if not compensar(s, saga_id)]
    if sin_cancelar:
        guardar_estado(saga_id, "REQUIERE_ATENCION", f"cancelación del cliente; no se pudo cancelar: {sin_cancelar}")
    else:
        guardar_estado(saga_id, "CANCELADA", "cancelada por el cliente: " + ", ".join(servicios) + " liberados")
    with psycopg.connect(DB) as conn:
        return a_dict(conn.execute(f"{SELECT} WHERE id = %s", (saga_id,)).fetchone())
