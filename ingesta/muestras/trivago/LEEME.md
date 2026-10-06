# Muestras de Trivago (respaldo)

El flow descarga Trivago **en vivo** (páginas de destino `/es-CO/odr/...`, ver `ingesta/trivago.py`).
Si en alguna ciudad Trivago bloquea al bot (HTTP 403/429 o desafío anti-bot) o la descarga falla, el flow usa
como **respaldo** la página de esa ciudad guardada aquí. Esos alojamientos aparecen con `fuente: "trivago-muestra"`.

## ¿Necesito guardar muestras?

Primero prueba la descarga en vivo (no toca la BD):

```bash
docker compose exec ingesta python trivago.py --probar
```

- Si las 3 ciudades muestran hoteles: no necesitas muestras.
- Si alguna dice `HTTP 403` o `desafío anti-bot`: guarda la página de esa ciudad como se indica abajo.

## Cómo guardar una muestra

1. En el navegador abre la página de destino de la ciudad:
   - Medellín: https://www.trivago.com.co/es-CO/odr/hoteles-medell%C3%ADn-colombia?search=200-65524
   - Cartagena: https://www.trivago.com.co/es-CO/odr/hoteles-cartagena-colombia?search=200-65529
   - Santa Marta: https://www.trivago.com.co/es-CO/odr/hoteles-santa-marta-colombia?search=200-65542
2. Haz **scroll hasta el final** para que carguen todos los hoteles.
3. Guarda la página: `Ctrl+S` → *Página web, solo HTML* (o DevTools → clic derecho sobre `<html>` → *Copy outerHTML*).
4. Recórtala con el código de ciudad al inicio del nombre (`MDE`, `CTG` o `SMR`):

   ```bash
   cd ingesta
   python trivago.py ~/Descargas/pagina-trivago.html muestras/trivago/MDE-medellin.html
   ```

   Solo necesita `pip install beautifulsoup4`. Sin Python, copia la página como `ingesta/muestras/original.html` y desde la raíz del repo:
   `docker compose run --rm ingesta python trivago.py muestras/original.html muestras/trivago/MDE-medellin.html` (luego borra `original.html`).

5. No hace falta reconstruir la imagen: la carpeta está montada como volumen. Se usará en la siguiente ejecución del flow.

`MIA-miami-ejemplo.html` es solo un ejemplo del formato: Miami no tiene vuelos ni autos en el sistema, así que nunca se usa.
