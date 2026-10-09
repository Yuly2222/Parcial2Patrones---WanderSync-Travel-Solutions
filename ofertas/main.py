# Microservicio de Ofertas: ofertas de proveedores externos (Booking.com) por categoría
# (alojamiento, vuelos, alquiler de coches y atracciones).
# Es dueño de su propia base de datos ("ofertas"), igual que los demás servicios (database per service).
# Los datos los escribe la ingesta (Prefect + Dask); este servicio solo los lee y los sirve al Gateway.
import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

DB = os.environ["DATABASE_URL"]  # apunta a la base de datos "ofertas"

CATEGORIAS = ("alojamiento", "vuelos", "coches", "atracciones")

# La base y la tabla se crean al arrancar si no existen: así el servicio funciona también sobre un volumen de
# Postgres creado antes de que existiera (db/init.sql solo se ejecuta la primera vez que se crea el volumen).
ESQUEMA = """
CREATE TABLE IF NOT EXISTS ofertas (
    categoria    TEXT NOT NULL,              -- alojamiento | vuelos | coches | atracciones
    llave        TEXT NOT NULL,              -- dest_id de Booking (o el destino / la atracción normalizados)
    destino      TEXT NOT NULL,              -- "Medellín", "Madrid"...
    titulo       TEXT,                       -- "Bogotá → Medellín", "Tour a pie por La Candelaria"...
    detalle      TEXT,                       -- "Colombia", "8 puntos de alquiler de coches"...
    ciudad       TEXT,                       -- MDE | CTG | SMR si el destino es una ciudad del sistema
    cantidad     INT,                        -- número de ofertas que Booking tiene en ese destino
    precio_desde NUMERIC(12, 2) NOT NULL,    -- precio "desde", en COP
    unidad       TEXT,                       -- "por noche", "por día"...
    campana      TEXT,                       -- título de la campaña ("Ahorra un 15% para finales de año")
    url          TEXT,
    fuente       TEXT NOT NULL DEFAULT 'booking-muestra',
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (categoria, llave)           -- llave del UPSERT de la ingesta: re-procesar no duplica
);
-- Columnas agregadas después de la primera versión (tablas ya creadas en volúmenes existentes)
ALTER TABLE ofertas ADD COLUMN IF NOT EXISTS titulo TEXT;
ALTER TABLE ofertas ADD COLUMN IF NOT EXISTS detalle TEXT;
DELETE FROM ofertas WHERE categoria NOT IN ('alojamiento', 'vuelos', 'coches', 'atracciones');
"""


def preparar_bd():
    nombre = conninfo_to_dict(DB)["dbname"]
    try:
        psycopg.connect(DB).close()
    except psycopg.OperationalError as e:
        if "does not exist" not in str(e):
            raise
        # CREATE DATABASE no puede ir dentro de una transacción -> autocommit, conectado a la BD "postgres"
        with psycopg.connect(make_conninfo(DB, dbname="postgres"), autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
    with psycopg.connect(DB) as conn:
        conn.execute(ESQUEMA)


@asynccontextmanager
async def ciclo_de_vida(app):
    preparar_bd()
    yield


app = FastAPI(lifespan=ciclo_de_vida)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ofertas")
def listar_ofertas(categoria: str | None = None):
    """Ofertas de una categoría (o de todas), las de ciudades del sistema primero y luego por precio."""
    if categoria is not None and categoria not in CATEGORIAS:
        raise HTTPException(status_code=422, detail=f"categoria debe ser una de {list(CATEGORIAS)}")
    with psycopg.connect(DB) as conn:
        filas = conn.execute(
            "SELECT categoria, llave, destino, ciudad, titulo, detalle, cantidad, precio_desde, unidad, campana, url, fuente, actualizado "
            "FROM ofertas WHERE %s::text IS NULL OR categoria = %s "
            "ORDER BY categoria, (ciudad IS NULL), precio_desde",
            (categoria, categoria),
        ).fetchall()
    campos = ("categoria", "llave", "destino", "ciudad", "titulo", "detalle", "cantidad", "precio_desde", "unidad", "campana", "url", "fuente", "actualizado")
    return [dict(zip(campos, f)) for f in filas]
