// Utilidades de presentación.

const cop = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

export const pesos = (n) => cop.format(n);

// "1 noche" / "3 noches"
export const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

// MODO DEMO: los clientes ven una interfaz limpia. Para la sustentación, abrir la app con ?demo
// (http://localhost:3000/?demo) muestra además el panel técnico de la SAGA, el Inspector GraphQL
// y los accesos a Prefect, Dask y GraphiQL.
export const DEMO = typeof window !== "undefined" && new URLSearchParams(window.location.search).has("demo");

// Nombres de los destinos por código IATA (el de las tablas de vuelos, hoteles y autos).
// Los trae el Gateway (query destinos, con el nombre que da Booking); estos son el respaldo mientras cargan.
const NOMBRES = new Map([
  ["MDE", "Medellín"],
  ["CTG", "Cartagena"],
  ["SMR", "Santa Marta"],
  ["BOG", "Bogotá"],
]);

/** Registra los nombres que llegan del Gateway, para que nombreCiudad() los use en toda la app. */
export function registrarNombres(destinos) {
  for (const d of destinos ?? []) if (d.nombre) NOMBRES.set(d.codigo, d.nombre);
}

export const nombreCiudad = (codigo) => NOMBRES.get(codigo) ?? codigo;

// "Medellín" -> "medellin": para comparar nombres y filtrar sin importar tildes ni mayúsculas
export const normalizar = (texto = "") =>
  texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();

/**
 * Reconstruye la línea de tiempo de la SAGA a partir de lo que devuelve el Gateway
 * (estado final + descripción del último paso que guardó el orquestador en la tabla sagas).
 *
 * El orquestador ejecuta vuelos -> hoteles -> autos. Si un paso falla, compensa en ORDEN INVERSO
 * todo lo que intentó, incluido el paso que falló (por si alcanzó a reservar antes de un timeout).
 */
export const PASOS = ["vuelos", "hoteles", "autos"];

// conAuto = false en destinos sin alquiler de autos: la SAGA solo tiene vuelo y hotel.
// CANCELADA = el cliente canceló una reserva confirmada: todo se reservó y luego se liberó en orden inverso.
export function lineaDeTiempo(estado, paso = "", conAuto = true) {
  const servicios = conAuto ? PASOS : PASOS.slice(0, 2);
  if (estado === "CONFIRMADA") {
    return { pasos: servicios.map((s) => ({ servicio: s, estado: "ok" })), compensaciones: [] };
  }
  if (estado === "CANCELADA" || (estado === "REQUIERE_ATENCION" && /cancelación del cliente/.test(paso ?? ""))) {
    const sinCancelar = paso?.match(/no se pudo cancelar: \[(.*)\]/)?.[1] ?? "";
    return {
      pasos: servicios.map((s) => ({ servicio: s, estado: "revertido" })),
      compensaciones: [...servicios].reverse().map((s) => ({ servicio: s, ok: !sinCancelar.includes(`'${s}'`) })),
    };
  }
  const fallo = paso?.match(/falló (\w+)/)?.[1];
  if ((estado === "COMPENSADA" || estado === "REQUIERE_ATENCION") && servicios.includes(fallo)) {
    const i = servicios.indexOf(fallo);
    const sinCancelar = paso.match(/no se pudo cancelar: \[(.*)\]/)?.[1] ?? "";
    return {
      pasos: servicios.map((s, j) => ({
        servicio: s,
        estado: j < i ? "revertido" : j === i ? "error" : "omitido",
      })),
      compensaciones: servicios.slice(0, i + 1)
        .reverse()
        .map((s) => ({ servicio: s, ok: !sinCancelar.includes(`'${s}'`) })),
    };
  }
  // EN_CURSO / COMPENSANDO: todavía no hay resultado final
  return { pasos: servicios.map((s) => ({ servicio: s, estado: "pendiente" })), compensaciones: [] };
}
