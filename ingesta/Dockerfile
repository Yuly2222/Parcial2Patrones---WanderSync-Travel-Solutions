# UNA sola imagen para 4 contenedores: servidor de Prefect, scheduler de Dask, workers de Dask y el flow.
# Usar la misma imagen garantiza que todos tengan EXACTAMENTE las mismas versiones de Dask y Prefect
# (si el scheduler y los workers tienen versiones distintas, Dask falla al serializar tareas)
# y que los workers tengan el código (flow.py) y las librerías (httpx, bs4, psycopg) que necesitan las tareas.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Sin CMD: cada servicio del docker-compose.yml define su propio "command".
