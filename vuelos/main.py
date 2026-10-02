import os                    # Para leer variables de entorno (la URL de la BD)
import psycopg               # Driver de PostgreSQL para Python
from fastapi import FastAPI  # Framework web

# "app" es el servidor web. El Dockerfile la arranca con: uvicorn main:app
app = FastAPI()

# La URL de la BD NO se escribe en el código: viene del docker-compose.yml (variable DATABASE_URL).
# Así las credenciales quedan fuera del repositorio del código (seguridad por diseño).
DB = os.environ["DATABASE_URL"]


# Cuando alguien haga GET a /health, se ejecuta esta función.
# Sirve para comprobar que el servicio está vivo.
@app.get("/health")
def health():
    return {"status": "ok"}  # FastAPI convierte el diccionario en JSON automáticamente


# EJEMPLO de lectura desde la BD (la tabla "aerolineas" aún no existe, así que este endpoint fallará por ahora).
@app.get("/aerolineas")
def listar_aerolineas():
    # "with" abre la conexión y la cierra sola al terminar, incluso si ocurre un error
    with psycopg.connect(DB) as conn:
        # fetchall() devuelve una lista de tuplas, ej: [(1, "Avianca"), (2, "LATAM")]
        filas = conn.execute("SELECT id, nombre FROM aerolineas").fetchall()
    # Convertimos cada tupla en un diccionario para que el JSON tenga nombres de campo legibles
    return [{"id": f[0], "nombre": f[1]} for f in filas]


# Lista los vuelos disponibles. Mismo patrón que listar_aerolineas().
@app.get("/vuelos")
def listar_vuelos():
    with psycopg.connect(DB) as conn:
        filas = conn.execute("SELECT id, origen, destino, precio FROM vuelos").fetchall()
    # f[0], f[1], f[2], f[3] siguen el MISMO orden de las columnas del SELECT
    return [{"id": f[0], "origen": f[1], "destino": f[2], "precio": f[3]} for f in filas]
