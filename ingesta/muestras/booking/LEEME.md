# Ofertas de Booking (páginas guardadas)

Booking.com responde con un desafío anti-bot (AWS WAF) incluso a su `robots.txt`, así que **no se descarga
nada automáticamente** (RFC 9309: si el robots.txt no se puede leer, el bot debe asumir que no tiene permiso).
Las ofertas salen de páginas que una persona guarda desde su navegador.

## Cómo agregar o actualizar una categoría

1. Abre la página de ofertas de Booking de esa pestaña y haz scroll hasta el final.
2. `Ctrl+S` → **"Página web, solo HTML"** → guárdala en esta carpeta con su nombre:

   | Pestaña | Archivo |
   |---|---|
   | Alojamiento | `booking-alojamiento.html` |
   | Vuelos | `booking-vuelos.html` |
   | Alquiler de coches | `booking-coches.html` |
   | Atracciones | `booking-atracciones.html` |

3. Recórtala (de ~1,2 MB a unos KB; la recortada queda en `recortadas/`, que es la que se sube al repo):

   ```bash
   docker compose exec ingesta python booking.py muestras/booking/booking-alojamiento.html muestras/booking/booking-vuelos.html muestras/booking/booking-coches.html muestras/booking/booking-atracciones.html
   ```

   Imprime cuántas ofertas encontró. Si dice 0, esa página tiene otra estructura: hay que ajustar `booking.py`.

4. Lanza el flow en Prefect (*Quick run*). Las ofertas aparecen en la sección "Ofertas" del frontend.

Vuelos: aunque la página muestra 10 tarjetas, trae los 50 destinos en sus datos internos; el parser los lee todos.

Atracciones: Booking carga las tarjetas a medida que bajas; la página general trae solo la primera. Para más
atracciones, haz scroll hasta el final antes de guardar (o guarda la de cada ciudad).

Las páginas completas (`booking-*.html` de esta carpeta) y sus carpetas `_files` no se suben al repo (`.gitignore`).
