# Microservicio de Autos. Misma estructura que vuelos/main.py (ver los comentarios detallados allá),
# más el interruptor para SIMULAR UN FALLO y demostrar las compensaciones de la SAGA.
import os
from contextlib import asynccontextmanager
from uuid import UUID
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DB = os.environ["DATABASE_URL"]  # apunta a la base de datos "autos"

# Migración idempotente al arrancar (ver vuelos/main.py). La ingesta carga el precio medio de alquiler
# de Booking por ciudad con UPSERT por (ciudad, modelo).
MIGRACION = """
ALTER TABLE autos ADD COLUMN IF NOT EXISTS fuente TEXT NOT NULL DEFAULT 'semilla';
ALTER TABLE autos ADD COLUMN IF NOT EXISTS actualizado TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS autos_ciudad_modelo ON autos (ciudad, modelo);
"""


@asynccontextmanager
async def ciclo_de_vida(app):
    with psycopg.connect(DB) as conn:
        conn.execute(MIGRACION)
    yield


app = FastAPI(lifespan=ciclo_de_vida)

# Interruptor de la demo: si la variable de entorno vale "true", toda reserva de auto falla.
# Se controla desde docker-compose.yml (ver el README / instrucciones de la demo).
FORZAR_FALLO = os.environ.get("FORZAR_FALLO_AUTOS", "false").lower() == "true"


@app.get("/health")
def health():
    return {"status": "ok", "forzar_fallo": FORZAR_FALLO}


# Filtro opcional: /autos?ciudad=MDE (mismo patrón que /vuelos?destino=)
@app.get("/autos")
def listar_autos(ciudad: str | None = None):
    with psycopg.connect(DB) as conn:
        filas = conn.execute(
            "SELECT id, modelo, ciudad, precio_dia, fuente FROM autos WHERE %s::text IS NULL OR ciudad = %s "
            "ORDER BY precio_dia",
            (ciudad, ciudad),
        ).fetchall()
    return [{"id": f[0], "modelo": f[1], "ciudad": f[2], "precio_dia": f[3], "fuente": f[4]} for f in filas]


@app.get("/autos/{auto_id}")
def ver_auto(auto_id: int):
    with psycopg.connect(DB) as conn:
        f = conn.execute("SELECT id, modelo, ciudad, precio_dia, fuente FROM autos WHERE id = %s", (auto_id,)).fetchone()
    if f is None:
        raise HTTPException(status_code=404, detail="Auto no encontrado")
    return {"id": f[0], "modelo": f[1], "ciudad": f[2], "precio_dia": f[3], "fuente": f[4]}


class Reserva(BaseModel):
    saga_id: UUID
    auto_id: int


# ACCIÓN de la SAGA
@app.post("/reservas")
def reservar(r: Reserva):
    if FORZAR_FALLO:
        # 503 = "servicio no disponible": simula que el proveedor de autos se cayó.
        # El orquestador lo detecta y dispara las compensaciones de hotel y vuelo.
        raise HTTPException(status_code=503, detail="Fallo simulado en el servicio de Autos")
    with psycopg.connect(DB) as conn:
        conn.execute(
            "INSERT INTO reservas (saga_id, auto_id, estado) VALUES (%s, %s, 'CONFIRMADA') "
            "ON CONFLICT (saga_id) DO NOTHING",
            (r.saga_id, r.auto_id),
        )
    return {"saga_id": r.saga_id, "estado": "CONFIRMADA"}


# COMPENSACIÓN de la SAGA. Ojo: NO depende de FORZAR_FALLO; cancelar siempre debe poder ejecutarse.
@app.post("/reservas/{saga_id}/cancelar")
def cancelar(saga_id: UUID):
    with psycopg.connect(DB) as conn:
        conn.execute("UPDATE reservas SET estado = 'CANCELADA' WHERE saga_id = %s", (saga_id,))
    return {"saga_id": saga_id, "estado": "CANCELADA"}
