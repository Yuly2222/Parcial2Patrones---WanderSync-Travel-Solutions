# Microservicio de Órdenes = ORQUESTADOR de la SAGA.
# Es el "director": llama en orden a Vuelos -> Hoteles -> Autos y, si alguno falla,
# ejecuta las compensaciones en orden inverso. Toda la lógica de la SAGA vive SOLO aquí.
import os
import time
import uuid
import httpx                    # Cliente HTTP para llamar a los otros microservicios
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI()
DB = os.environ["DATABASE_URL"]  # apunta a la base de datos "ordenes" (tabla sagas)


class Orden(BaseModel):
    vuelo_id: int
    hotel_id: int
    auto_id: int
    personas: int = Field(default=1, ge=1, le=9)   # Field valida el rango: fuera de 1-9 FastAPI responde 422


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
            "INSERT INTO sagas (id, vuelo_id, hotel_id, auto_id, personas, estado, paso) "
            "VALUES (%s, %s, %s, %s, %s, 'EN_CURSO', 'inicio')",
            (saga_id, orden.vuelo_id, orden.hotel_id, orden.auto_id, orden.personas),
        )

    # 2) Los pasos de la SAGA, EN ORDEN: (servicio, datos que necesita para reservar)
    pasos = [
        ("vuelos",  {"vuelo_id": orden.vuelo_id}),
        ("hoteles", {"hotel_id": orden.hotel_id}),
        ("autos",   {"auto_id": orden.auto_id}),
    ]

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
    guardar_estado(saga_id, "CONFIRMADA", "vuelo, hotel y auto reservados")
    return {"saga_id": saga_id, "estado": "CONFIRMADA"}


# Consultar cómo va / cómo terminó una SAGA
@app.get("/ordenes/{saga_id}")
def ver_orden(saga_id: uuid.UUID):
    with psycopg.connect(DB) as conn:
        fila = conn.execute(
            "SELECT estado, paso, actualizado, personas FROM sagas WHERE id = %s", (saga_id,)
        ).fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return {"saga_id": saga_id, "estado": fila[0], "paso": fila[1], "actualizado": fila[2], "personas": fila[3]}
