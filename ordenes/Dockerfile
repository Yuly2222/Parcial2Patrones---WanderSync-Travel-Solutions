# Imagen base: Python 3.12 en versión "slim" (sin herramientas extra -> imagen más liviana y con menos superficie de ataque)
FROM python:3.12-slim

# Carpeta de trabajo dentro del contenedor; los comandos siguientes se ejecutan aquí
WORKDIR /app

# Copiamos SOLO requirements.txt primero: si el código cambia pero las dependencias no,
# Docker reutiliza la capa cacheada del pip install y el build es mucho más rápido
COPY requirements.txt .

# Instala las dependencias; --no-cache-dir evita guardar el caché de pip dentro de la imagen
RUN pip install --no-cache-dir -r requirements.txt

# Ahora sí copiamos el resto del código del servicio
COPY . .

# Comando al arrancar el contenedor: uvicorn sirve la variable "app" del archivo "main.py".
# --host 0.0.0.0 es obligatorio: con 127.0.0.1 solo se aceptarían conexiones desde dentro del propio contenedor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
