# Microservicio de Hoteles. Misma estructura que vuelos/main.py (ver los comentarios detallados allá).
import os
from uuid import UUID
import psycopg
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
DB = os.environ["DATABASE_URL"]  # apunta a la base de datos "hoteles" (ver docker-compose.yml)


@app.get("/health")
def health():
    return {"status": "ok"}


# Filtro opcional: /hoteles?ciudad=MDE (mismo patrón que /vuelos?destino=)
@app.get("/hoteles")
def listar_hoteles(ciudad: str | None = None):
    with psycopg.connect(DB) as conn:
        filas = conn.execute(
            "SELECT id, nombre, ciudad, precio_noche FROM hoteles WHERE %s::text IS NULL OR ciudad = %s",
            (ciudad, ciudad),
        ).fetchall()
    return [{"id": f[0], "nombre": f[1], "ciudad": f[2], "precio_noche": f[3]} for f in filas]


class Reserva(BaseModel):
    saga_id: UUID
    hotel_id: int


# ACCIÓN de la SAGA (idempotente gracias a ON CONFLICT sobre saga_id)
@app.post("/reservas")
def reservar(r: Reserva):
    with psycopg.connect(DB) as conn:
        conn.execute(
            "INSERT INTO reservas (saga_id, hotel_id, estado) VALUES (%s, %s, 'CONFIRMADA') "
            "ON CONFLICT (saga_id) DO NOTHING",
            (r.saga_id, r.hotel_id),
        )
    return {"saga_id": r.saga_id, "estado": "CONFIRMADA"}


# COMPENSACIÓN de la SAGA (cambia estado, no borra; idempotente)
@app.post("/reservas/{saga_id}/cancelar")
def cancelar(saga_id: UUID):
    with psycopg.connect(DB) as conn:
        conn.execute("UPDATE reservas SET estado = 'CANCELADA' WHERE saga_id = %s", (saga_id,))
    return {"saga_id": saga_id, "estado": "CANCELADA"}
