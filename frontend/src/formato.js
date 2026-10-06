// Utilidades de presentación.

const cop = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

export const pesos = (n) => cop.format(n);

// "1 noche" / "3 noches"
export const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

// MODO DEMO: los clientes ven una interfaz limpia. Para la sustentación, abrir la app con ?demo
// (http://localhost:3000/?demo) muestra además el panel técnico de la SAGA, el Inspector GraphQL
// y los accesos a Prefect, Dask y GraphiQL.
export const DEMO = typeof window !== "undefined" && new URLSearchParams(window.location.search).has("demo");

// Códigos de ciudad que usan las tablas de vuelos, hoteles y autos (ver db/init.sql)
export const DESTINOS = [
  { codigo: "MDE", nombre: "Medellín", lema: "Valle de Aburrá" },
  { codigo: "CTG", nombre: "Cartagena", lema: "Caribe amurallado" },
  { codigo: "SMR", nombre: "Santa Marta", lema: "Sierra y mar" },
];

export const nombreCiudad = (codigo) => DESTINOS.find((d) => d.codigo === codigo)?.nombre ?? codigo;

/**
 * Reconstruye la línea de tiempo de la SAGA a partir de lo que devuelve el Gateway
 * (estado final + descripción del último paso que guardó el orquestador en la tabla sagas).
 *
 * El orquestador ejecuta vuelos -> hoteles -> autos. Si un paso falla, compensa en ORDEN INVERSO
 * todo lo que intentó, incluido el paso que falló (por si alcanzó a reservar antes de un timeout).
 */
export const PASOS = ["vuelos", "hoteles", "autos"];

export function lineaDeTiempo(estado, paso = "") {
  if (estado === "CONFIRMADA") {
    return { pasos: PASOS.map((s) => ({ servicio: s, estado: "ok" })), compensaciones: [] };
  }
  const fallo = paso?.match(/falló (\w+)/)?.[1];
  if ((estado === "COMPENSADA" || estado === "REQUIERE_ATENCION") && PASOS.includes(fallo)) {
    const i = PASOS.indexOf(fallo);
    const sinCancelar = paso.match(/no se pudo cancelar: \[(.*)\]/)?.[1] ?? "";
    return {
      pasos: PASOS.map((s, j) => ({
        servicio: s,
        estado: j < i ? "revertido" : j === i ? "error" : "omitido",
      })),
      compensaciones: PASOS.slice(0, i + 1)
        .reverse()
        .map((s) => ({ servicio: s, ok: !sinCancelar.includes(`'${s}'`) })),
    };
  }
  // EN_CURSO / COMPENSANDO: todavía no hay resultado final
  return { pasos: PASOS.map((s) => ({ servicio: s, estado: "pendiente" })), compensaciones: [] };
}
