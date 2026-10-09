import os                       # Para leer variables de entorno (la URL de la BD)
from contextlib import asynccontextmanager
from uuid import UUID           # Tipo para los identificadores de SAGA
import psycopg                  # Driver de PostgreSQL para Python
from fastapi import FastAPI, HTTPException     # Framework web
from pydantic import BaseModel  # Valida automáticamente el JSON que nos envían

# La URL de la BD NO se escribe en el código: viene del docker-compose.yml (variable DATABASE_URL).
# Así las credenciales quedan fuera del código (seguridad por diseño).
DB = os.environ["DATABASE_URL"]

# MIGRACIÓN al arrancar. db/init.sql solo corre la primera vez que se crea el volumen de Postgres; estas
# sentencias son idempotentes (IF NOT EXISTS), así que actualizan una BD ya creada sin borrar nada.
# fuente + índice único: la ingesta (Prefect) carga los vuelos de Booking con UPSERT por ruta y fuente.
MIGRACION = """
ALTER TABLE vuelos ADD COLUMN IF NOT EXISTS fuente TEXT NOT NULL DEFAULT 'semilla';
ALTER TABLE vuelos ADD COLUMN IF NOT EXISTS actualizado TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS vuelos_ruta_fuente ON vuelos (origen, destino, fuente);
ALTER TABLE vuelos ADD COLUMN IF NOT EXISTS destino_nombre TEXT;   -- "Ciudad de México" (de la página de Booking)
ALTER TABLE vuelos ADD COLUMN IF NOT EXISTS pais TEXT;             -- "México"
"""


@asynccontextmanager
async def ciclo_de_vida(app):
    with psycopg.connect(DB) as conn:
        conn.execute(MIGRACION)
    yield


# "app" es el servidor web. El Dockerfile la arranca con: uvicorn main:app
app = FastAPI(lifespan=ciclo_de_vida)


# Cuando alguien haga GET a /health, se ejecuta esta función.
# Sirve para comprobar que el servicio está vivo.
@app.get("/health")
def health():
    return {"status": "ok"}  # FastAPI convierte el diccionario en JSON automáticamente


# EJEMPLO de lectura desde la BD.
@app.get("/aerolineas")
def listar_aerolineas():
    # "with" abre la conexión y la cierra sola al terminar, incluso si ocurre un error
    with psycopg.connect(DB) as conn:
        # fetchall() devuelve una lista de tuplas, ej: [(1, "Avianca"), (2, "LATAM")]
        filas = conn.execute("SELECT id, nombre FROM aerolineas").fetchall()
    # Convertimos cada tupla en un diccionario para que el JSON tenga nombres de campo legibles
    return [{"id": f[0], "nombre": f[1]} for f in filas]


# Lista los vuelos disponibles. Mismo patrón que listar_aerolineas().
# "destino" es un filtro OPCIONAL por query string: /vuelos?destino=MDE
# Filtrar aquí (en la BD) y no en el Gateway evita mandar por la red datos que nadie pidió.
@app.get("/vuelos")
def listar_vuelos(destino: str | None = None):
    with psycopg.connect(DB) as conn:
        # Si destino es NULL (no lo enviaron) la condición es verdadera para todas las filas -> lista todo
        filas = conn.execute(
            "SELECT id, origen, destino, precio, fuente FROM vuelos WHERE %s::text IS NULL OR destino = %s "
            "ORDER BY precio",
            (destino, destino),
        ).fetchall()
    # f[0], f[1], f[2]... siguen el MISMO orden de las columnas del SELECT
    return [{"id": f[0], "origen": f[1], "destino": f[2], "precio": f[3], "fuente": f[4]} for f in filas]


# Un vuelo por id: el Gateway lo usa al reservar para calcular el precio en el servidor
# (nunca se confía en un precio que mande el navegador).
@app.get("/vuelos/{vuelo_id}")
def ver_vuelo(vuelo_id: int):
    with psycopg.connect(DB) as conn:
        f = conn.execute("SELECT id, origen, destino, precio, fuente FROM vuelos WHERE id = %s", (vuelo_id,)).fetchone()
    if f is None:
        raise HTTPException(status_code=404, detail="Vuelo no encontrado")
    return {"id": f[0], "origen": f[1], "destino": f[2], "precio": f[3], "fuente": f[4]}


# Ciudades a las que hay al menos un vuelo, con su nombre y país (el Gateway las cruza con las ciudades que
# tienen hoteles). max() toma el nombre de la fila que lo tenga (los vuelos semilla no traen nombre).
@app.get("/destinos")
def listar_destinos():
    with psycopg.connect(DB) as conn:
        filas = conn.execute(
            "SELECT destino, max(destino_nombre), max(pais), min(precio) FROM vuelos GROUP BY destino ORDER BY destino"
        ).fetchall()
    return [{"codigo": f[0], "nombre": f[1], "pais": f[2], "vuelo_desde": f[3]} for f in filas]


# ---------------- Endpoints que usa la SAGA ----------------

# Forma del JSON que esperamos al reservar. Si falta un campo o el tipo es incorrecto,
# FastAPI responde 422 automáticamente sin ejecutar nuestro código.
class Reserva(BaseModel):
    saga_id: UUID
    vuelo_id: int


# ACCIÓN de la SAGA: reservar el vuelo.
@app.post("/reservas")
def reservar(r: Reserva):
    with psycopg.connect(DB) as conn:   # al salir del "with" sin errores se hace COMMIT automático
        # ON CONFLICT (saga_id) DO NOTHING = IDEMPOTENCIA: si el orquestador reintenta
        # con el mismo saga_id, no se crea una segunda reserva.
        # Los %s se reemplazan de forma segura por los valores (evita inyección SQL; NUNCA usar f-strings aquí).
        conn.execute(
            "INSERT INTO reservas (saga_id, vuelo_id, estado) VALUES (%s, %s, 'CONFIRMADA') "
            "ON CONFLICT (saga_id) DO NOTHING",
            (r.saga_id, r.vuelo_id),
        )
    return {"saga_id": r.saga_id, "estado": "CONFIRMADA"}


# COMPENSACIÓN de la SAGA: cancelar la reserva.
# No borra la fila, cambia el estado (trazabilidad). Es idempotente por naturaleza:
# cancelar dos veces deja el mismo resultado, y cancelar algo que no existe no hace nada.
@app.post("/reservas/{saga_id}/cancelar")
def cancelar(saga_id: UUID):
    with psycopg.connect(DB) as conn:
        conn.execute("UPDATE reservas SET estado = 'CANCELADA' WHERE saga_id = %s", (saga_id,))
    return {"saga_id": saga_id, "estado": "CANCELADA"}
