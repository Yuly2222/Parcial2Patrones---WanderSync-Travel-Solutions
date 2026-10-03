-- Este script lo ejecuta Postgres UNA sola vez, al crear la BD por primera vez.
-- Si lo modifican: docker compose down -v  (borra la BD)  y luego  docker compose up --build
--
-- Un solo servidor Postgres, pero UNA BASE DE DATOS POR MICROSERVICIO ("database per service").
-- Ningún servicio puede hacer JOIN ni una transacción sobre los datos de otro:
-- justamente por eso necesitamos el patrón SAGA para mantener la consistencia.

CREATE DATABASE vuelos;
CREATE DATABASE hoteles;
CREATE DATABASE autos;
CREATE DATABASE ordenes;
CREATE DATABASE auth;      -- usuarios y sesiones (la usa el Gateway)


-- ===================== VUELOS =====================
\c vuelos

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

-- Reservas de vuelo hechas por la SAGA.
-- saga_id es PRIMARY KEY = llave de IDEMPOTENCIA: si el orquestador reintenta, no se duplica la reserva.
-- Nunca se borran filas: la compensación cambia estado a CANCELADA (queda trazabilidad).
CREATE TABLE reservas (
    saga_id  UUID PRIMARY KEY,
    vuelo_id INT  NOT NULL REFERENCES vuelos(id),  -- REFERENCES: no deja reservar un vuelo que no existe
    estado   TEXT NOT NULL                         -- CONFIRMADA | CANCELADA
);


-- ===================== HOTELES =====================
\c hoteles

CREATE TABLE hoteles (
    id           SERIAL PRIMARY KEY,
    nombre       TEXT NOT NULL,
    ciudad       TEXT NOT NULL,
    precio_noche NUMERIC(12, 2) NOT NULL,
    rating       NUMERIC(4, 2),                    -- calificación 0-10 (puede no existir)
    url          TEXT UNIQUE,                      -- página de origen; UNIQUE = llave para el UPSERT del scraper
                                                   -- (re-scrapear actualiza el precio en vez de duplicar el hotel)
    fuente       TEXT NOT NULL DEFAULT 'semilla',  -- 'semilla' (datos de prueba) | 'hostelworld' (scraping real)
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Datos semilla: permiten probar el sistema aunque el scraper aún no haya corrido.
INSERT INTO hoteles (nombre, ciudad, precio_noche) VALUES
    ('Hotel Poblado Plaza', 'MDE', 280000),
    ('Hotel Caribe',        'CTG', 450000),
    ('Hotel Irotama',       'SMR', 390000);

CREATE TABLE reservas (
    saga_id  UUID PRIMARY KEY,
    hotel_id INT  NOT NULL REFERENCES hoteles(id),
    estado   TEXT NOT NULL
);


-- ===================== AUTOS =====================
\c autos

CREATE TABLE autos (
    id         SERIAL PRIMARY KEY,
    modelo     TEXT NOT NULL,
    ciudad     TEXT NOT NULL,
    precio_dia NUMERIC(12, 2) NOT NULL
);
INSERT INTO autos (modelo, ciudad, precio_dia) VALUES
    ('Kia Picanto',    'MDE', 120000),
    ('Renault Duster', 'CTG', 180000),
    ('Chevrolet Onix', 'SMR', 150000);

CREATE TABLE reservas (
    saga_id UUID PRIMARY KEY,
    auto_id INT  NOT NULL REFERENCES autos(id),
    estado  TEXT NOT NULL
);


-- ===================== ÓRDENES (orquestador SAGA) =====================
\c ordenes

-- Una fila por cada SAGA. Se actualiza en CADA paso: es la "bitácora" del orquestador
-- y la evidencia para la demo (se ve en qué paso iba y cómo terminó).
CREATE TABLE sagas (
    id          UUID PRIMARY KEY,
    vuelo_id    INT  NOT NULL,
    hotel_id    INT  NOT NULL,
    auto_id     INT  NOT NULL,
    estado      TEXT NOT NULL,   -- EN_CURSO | CONFIRMADA | COMPENSANDO | COMPENSADA | REQUIERE_ATENCION
    paso        TEXT,            -- descripción del último paso ejecutado
    actualizado TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ===================== AUTH (usuarios y sesiones del Gateway) =====================
\c auth

CREATE TABLE usuarios (
    id            SERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,          -- hash Argon2id (incluye sal y parámetros); NUNCA la contraseña
    creado        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sesiones del lado del servidor. El navegador solo guarda un token aleatorio en una cookie;
-- aquí se guarda el SHA-256 de ese token (si alguien roba la BD, no obtiene tokens utilizables).
CREATE TABLE sesiones (
    id         TEXT PRIMARY KEY,                                          -- SHA-256 del token de la cookie
    usuario_id INT  NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    expira     TIMESTAMPTZ NOT NULL
);
