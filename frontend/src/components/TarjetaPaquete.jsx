// Una combinación vuelo + hotel + auto (o vuelo + hotel donde no hay alquiler de autos),
// con el desglose del precio y el botón de reserva.
import { DEMO, pesos, plural, nombreCiudad } from "../formato";

// De dónde viene el precio del hotel (columna "fuente" de la BD de hoteles).
// El cliente solo ve el proveedor; en modo demo (?demo) se ve además cómo se obtuvo el dato.
const FUENTES = {
  hostelworld: {
    cliente: "Precio de Hostelworld",
    demo: "Hostelworld · en vivo",
    clase: "bg-musgo/20 text-selva",
    ayuda: "Precio real descargado por el scraper (Dask + Prefect)",
  },
  trivago: {
    cliente: "Precio de Trivago",
    demo: "Trivago · en vivo",
    clase: "bg-mostaza/20 text-oliva-oscuro",
    ayuda: "Precio real descargado de Trivago con BeautifulSoup (Dask + Prefect)",
  },
  "trivago-muestra": {
    cliente: "Precio de Trivago",
    demo: "Trivago · muestra",
    clase: "bg-mostaza/20 text-oliva-oscuro",
    ayuda: "Respaldo: página de Trivago guardada desde el navegador, usada porque la descarga en vivo falló",
  },
  semilla: { cliente: null, demo: "Dato semilla", clase: "bg-niebla/60 text-acero", ayuda: "Dato de prueba de db/init.sql" },
};

function Tramo({ etiqueta, titulo, detalle, children, className = "" }) {
  return (
    <div className={`min-w-0 ${className}`}>
      <p className="text-[11px] font-semibold tracking-wider text-piedra uppercase">{etiqueta}</p>
      <p className="mt-0.5 truncate font-semibold text-tinta" title={typeof titulo === "string" ? titulo : undefined}>
        {titulo}
      </p>
      <p className="text-sm text-acero">{detalle}</p>
      {children}
    </div>
  );
}

export default function TarjetaPaquete({ paquete, noches, personas, onReservar, reservando, deshabilitado }) {
  const { vuelo, hotel, auto, precioTotal, habitaciones, autos } = paquete;
  const fuente = FUENTES[hotel.fuente] ?? FUENTES.semilla;
  const etiquetaFuente = DEMO ? fuente.demo : fuente.cliente;

  return (
    <article className="entrar grid gap-4 rounded-2xl border border-niebla bg-white p-4 sm:grid-cols-[1fr_auto] sm:p-5">
      {/* Celular: el hotel a lo ancho y debajo vuelo y auto lado a lado. Desde 640 px: las tres columnas */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 sm:gap-4">
        <Tramo
          etiqueta="Vuelo"
          titulo={
            <span className="font-mono">
              {vuelo.origen} <span className="text-mostaza">→</span> {vuelo.destino}
            </span>
          }
          detalle={personas > 1 ? `${pesos(vuelo.precio)} × ${personas} personas` : pesos(vuelo.precio)}
        >
          {vuelo.fuente === "booking-muestra" && (
            <span className="mt-1.5 inline-block rounded bg-[#2e5e8c]/10 px-1.5 py-0.5 text-xs font-medium text-[#2e5e8c]">
              {DEMO ? "Booking · página guardada" : "Precio de Booking"}
            </span>
          )}
        </Tramo>
        <Tramo
          etiqueta="Hotel"
          className="order-first col-span-2 sm:order-none sm:col-span-1"
          titulo={hotel.nombre}
          detalle={`${pesos(hotel.precioNoche)} / noche${habitaciones > 1 ? ` × ${habitaciones} hab.` : ""}`}
        >
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {hotel.rating != null && (
              <span className="rounded bg-selva px-1.5 py-0.5 font-mono text-xs font-medium text-papel">
                {hotel.rating.toFixed(1)}
              </span>
            )}
            {etiquetaFuente && (
              <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${fuente.clase}`} title={DEMO ? fuente.ayuda : undefined}>
                {etiquetaFuente}
              </span>
            )}
          </div>
        </Tramo>
        {auto ? (
          <Tramo
            etiqueta="Auto"
            titulo={auto.modelo}
            detalle={`${pesos(auto.precioDia)} / día${autos > 1 ? ` × ${autos} autos` : ""}`}
          />
        ) : (
          // San Andrés, Pereira...: Booking no tiene alquiler de autos ahí, el paquete es vuelo + hotel
          <Tramo etiqueta="Auto" titulo={<span className="text-piedra">Sin auto</span>} detalle="No hay alquiler en este destino" />
        )}
      </div>

      <div className="flex items-end justify-between gap-4 border-t border-niebla pt-4 sm:flex-col sm:items-end sm:border-t-0 sm:border-l sm:pt-0 sm:pl-5">
        <div className="sm:text-right">
          <p className="text-xs text-piedra">
            {plural(noches, "noche", "noches")} · {plural(personas, "persona", "personas")} en {nombreCiudad(vuelo.destino)}
          </p>
          <p className="font-display text-2xl font-semibold tracking-tight text-oliva-oscuro">{pesos(precioTotal)}</p>
          {personas > 1 && <p className="text-xs text-acero">{pesos(precioTotal / personas)} por persona</p>}
        </div>
        <button
          onClick={() => onReservar(paquete)}
          disabled={deshabilitado}
          className="shrink-0 rounded-xl bg-selva px-4 py-2.5 text-sm font-semibold text-papel transition hover:bg-salvia disabled:cursor-not-allowed disabled:opacity-50"
        >
          {reservando ? "Reservando…" : "Reservar paquete"}
        </button>
      </div>
    </article>
  );
}
