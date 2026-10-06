// "Mis reservas": las reservas hechas en esta visita. "Ver estado" vuelve a consultarlas con la query orden(sagaId).
import { nombreCiudad, plural } from "../formato";
import { codigoReserva } from "./ResultadoReserva";

const ESTADOS = {
  CONFIRMADA: { texto: "Confirmada", punto: "bg-musgo" },
  COMPENSADA: { texto: "No completada", punto: "bg-mostaza" },
  REQUIERE_ATENCION: { texto: "En revisión", punto: "bg-[#b4553f]" },
};

export default function Historial({ reservas, onConsultar }) {
  if (reservas.length === 0) return null;
  return (
    <section className="rounded-2xl border border-niebla bg-white p-5">
      <h2 className="font-display text-lg font-semibold">Mis reservas</h2>
      <ul className="mt-3 divide-y divide-niebla/70">
        {reservas.map((r) => {
          const e = ESTADOS[r.estado] ?? { texto: "En proceso", punto: "bg-niebla" };
          return (
            <li key={r.sagaId} className="flex items-center gap-3 py-2.5 text-sm">
              <span className={`size-2 shrink-0 rounded-full ${e.punto}`} aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">
                  {nombreCiudad(r.ciudad)} · {r.hotel}
                </p>
                <p className="text-xs text-piedra">
                  {e.texto} · {plural(r.personas, "persona", "personas")} ·{" "}
                  <span className="font-mono whitespace-nowrap">{codigoReserva(r.sagaId)}</span>
                </p>
              </div>
              <button
                onClick={() => onConsultar(r.sagaId)}
                className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-acero hover:bg-papel hover:text-tinta"
              >
                Ver estado
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
