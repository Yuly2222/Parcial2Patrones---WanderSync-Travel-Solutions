-- Este script lo ejecuta Postgres UNA sola vez, al crear la BD por primera vez.
-- Si lo modifican: docker compose down -v  (borra la BD)  y luego  docker compose up --build

CREATE TABLE aerolineas (
    id     SERIAL PRIMARY KEY,   -- SERIAL = número que se autoincrementa solo (1, 2, 3...)
    nombre TEXT NOT NULL         -- NOT NULL = obligatorio
);
INSERT INTO aerolineas (nombre) VALUES ('Avianca'), ('LATAM');

CREATE TABLE vuelos (
    id      SERIAL PRIMARY KEY,
    origen  TEXT NOT NULL,           -- código IATA del aeropuerto, ej: BOG
    destino TEXT NOT NULL,
    precio  NUMERIC(12, 2) NOT NULL  -- NUMERIC y no FLOAT: FLOAT redondea en binario (0.1 + 0.2 = 0.30000000000000004);
                                     -- con dinero eso descuadra cuentas. (12, 2) = hasta 12 dígitos, 2 decimales
);
INSERT INTO vuelos (origen, destino, precio) VALUES
    ('BOG', 'MDE', 250000),
    ('BOG', 'CTG', 380000),
    ('MDE', 'SMR', 310000);
