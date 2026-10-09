// Tarjeta de una oferta de Booking.com (sección "Ofertas" y resultados de un destino sin paquetes).
// Si el destino tiene paquetes en WanderSync, el botón lleva a ellos; si no, a la oferta en Booking.
import { nombreCiudad, pesos } from "../formato";

export const CATEGORIAS = {
  alojamiento: "Alojamiento",
  vuelos: "Vuelo",
  coches: "Auto",
  atracciones: "Atracción",
};

export default function TarjetaOferta({
  oferta: o,
  conPaquetes,
  onVerPaquetes,
  mostrarCategoria = false,
  className = "",
}) {
  return (
    <li className={`flex min-w-0 flex-col rounded-2xl border border-niebla bg-white p-4 ${className}`}>
      {mostrarCategoria && (
        <p className="mb-1 text-[11px] font-semibold tracking-wider text-oliva uppercase">{CATEGORIAS[o.categoria]}</p>
      )}
      <div className="flex items-start justify-between gap-2">
        {/* Atracciones y vuelos traen un título propio ("Tour a pie…", "Bogotá → Medellín") */}
        <p className="min-w-0 font-semibold leading-tight break-words">{o.titulo ?? o.destino}</p>
        {conPaquetes && (
          <span className="shrink-0 rounded bg-musgo/20 px-1.5 py-0.5 text-[11px] font-semibold text-selva">
            {o.ciudad}
          </span>
        )}
      </div>
      {(o.titulo || o.detalle || o.cantidad != null) && (
        <p className="mt-0.5 text-xs text-piedra">
          {[
            o.cantidad != null && `${o.cantidad} ofertas`,
            o.detalle,
            o.titulo && o.categoria === "atracciones" && o.destino,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      )}
      <p className="mt-3 text-xs text-acero">Desde</p>
      <p className="font-display text-lg font-semibold tracking-tight text-oliva-oscuro sm:text-xl">
        {pesos(o.precioDesde)}
        {o.unidad && <span className="ml-1 font-sans text-xs font-normal text-acero">{o.unidad}</span>}
      </p>
      <div className="mt-auto pt-3">
        {conPaquetes ? (
          <button
            onClick={() => onVerPaquetes(o.ciudad)}
            className="w-full rounded-lg bg-selva px-2 py-2 text-sm font-semibold text-papel transition hover:bg-salvia"
          >
            Ver paquetes a {nombreCiudad(o.ciudad)}
          </button>
        ) : (
          o.url && (
            <a
              href={o.url}
              target="_blank"
              rel="noreferrer noopener"
              className="block w-full rounded-lg border border-niebla py-2 text-center text-sm font-medium text-acero transition hover:border-pizarra hover:text-tinta"
            >
              Ver en Booking <span aria-hidden="true">↗</span>
            </a>
          )
        )}
      </div>
    </li>
  );
}
