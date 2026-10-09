// "Ofertas del momento": ofertas de Booking.com por categoría, ingeridas por Prefect + Dask (servicio Ofertas).
// Las de ciudades con paquetes en WanderSync (query destinos) llevan a esos paquetes; las demás, a Booking.
// Las ofertas las carga App (también las usa el selector de destino) y llegan por props.
import { useEffect, useMemo, useState } from "react";
import { DEMO } from "../formato";
import TarjetaOferta from "./TarjetaOferta";

const PESTANAS = [
  ["alojamiento", "Alojamiento"],
  ["vuelos", "Vuelos"],
  ["coches", "Alquiler de coches"],
  ["atracciones", "Atracciones"],
];
const VISIBLES = 8; // tarjetas por tanda (vuelos trae 50 destinos y coches ~200 ciudades)

// true por debajo de 640 px (el breakpoint "sm" de Tailwind); se actualiza al girar o redimensionar
function useEnCelular() {
  const consulta = "(max-width: 639px)";
  const [movil, setMovil] = useState(() => typeof window !== "undefined" && window.matchMedia(consulta).matches);
  useEffect(() => {
    const mq = window.matchMedia(consulta);
    const cambio = (e) => setMovil(e.matches);
    mq.addEventListener("change", cambio);
    return () => mq.removeEventListener("change", cambio);
  }, []);
  return movil;
}

export default function Ofertas({ ofertas, conPaquetes, onVerPaquetes }) {
  const [pestana, setPestana] = useState(null);
  const [visibles, setVisibles] = useState(VISIBLES);
  const enCelular = useEnCelular();

  // Solo se muestran las pestañas que tienen ofertas
  const disponibles = useMemo(() => PESTANAS.filter(([c]) => ofertas?.some((o) => o.categoria === c)), [ofertas]);
  const activa = pestana ?? disponibles[0]?.[0];
  const lista = (ofertas ?? []).filter((o) => o.categoria === activa);
  const campana = lista.find((o) => o.campana)?.campana;

  if (!ofertas || disponibles.length === 0) return null;

  return (
    <section aria-labelledby="titulo-ofertas" className="border-b border-niebla bg-white/60">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
          <div className="min-w-0">
            <p className="text-xs font-semibold tracking-wider text-oliva uppercase">Vía Booking.com</p>
            <h2 id="titulo-ofertas" className="font-display text-xl font-semibold tracking-tight sm:text-2xl">
              {campana ?? "Ofertas del momento"}
            </h2>
          </div>
          {DEMO && (
            <p className="font-mono text-[11px] text-piedra">
              fuente: booking-muestra · servicio Ofertas · query ofertas
            </p>
          )}
        </div>

        {/* En pantallas angostas las pestañas se desplazan de lado (sin desbordar la página) */}
        <div
          role="tablist"
          aria-label="Tipo de oferta"
          className="-mx-4 mt-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0"
        >
          {disponibles.map(([c, nombre]) => (
            <button
              key={c}
              role="tab"
              aria-selected={c === activa}
              onClick={() => {
                setPestana(c);
                setVisibles(VISIBLES);
              }}
              className={`shrink-0 rounded-full border px-4 py-1.5 text-sm font-medium transition ${
                c === activa
                  ? "border-noche bg-noche text-papel"
                  : "border-niebla bg-white text-acero hover:border-pizarra"
              }`}
            >
              {nombre}
            </button>
          ))}
        </div>

        {/* Celular: carrusel que se desliza de lado (todas las ofertas, sin alargar la página).
            Desde 640 px: cuadrícula de 2 a 4 columnas con "Ver más" */}
        <ul className="-mx-4 mt-5 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:snap-none sm:grid-cols-2 sm:overflow-visible sm:px-0 sm:pb-0 md:grid-cols-3 lg:grid-cols-4">
          {lista.slice(0, enCelular ? undefined : visibles).map((o, i) => (
            <TarjetaOferta
              key={`${o.categoria}-${i}`}
              className="w-[78%] shrink-0 snap-start min-[480px]:w-[45%] sm:w-auto"
              oferta={o}
              conPaquetes={!!o.ciudad && conPaquetes.has(o.ciudad)}
              onVerPaquetes={onVerPaquetes}
            />
          ))}
        </ul>

        {!enCelular && lista.length > VISIBLES && (
          <button
            onClick={() => setVisibles((v) => (v >= lista.length ? VISIBLES : v + VISIBLES * 2))}
            className="mt-4 text-sm font-semibold text-selva underline-offset-2 hover:underline"
          >
            {visibles >= lista.length ? "Ver menos" : `Ver más (${lista.length - visibles} restantes)`}
          </button>
        )}
      </div>
    </section>
  );
}
