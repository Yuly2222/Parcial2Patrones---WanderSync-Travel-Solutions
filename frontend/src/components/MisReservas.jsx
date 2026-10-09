// "Mis reservas": las reservas del usuario guardadas en el servicio Órdenes (query misReservas), así siguen ahí
// al recargar la página o al entrar desde otro dispositivo. Cada una muestra su estado y permite:
//   - Actualizar: vuelve a consultar su estado (query orden)
//   - Cancelar:   solo las confirmadas (mutation cancelarReserva -> la SAGA libera auto, hotel y vuelo)
import { useState } from "react";
import { nombreCiudad, pesos, plural } from "../formato";
import { codigoReserva } from "./ResultadoReserva";

export const ESTADOS = {
  CONFIRMADA: { texto: "Confirmada", clase: "bg-musgo/25 text-selva" },
  COMPENSADA: { texto: "No completada", clase: "bg-mostaza/25 text-oliva-oscuro" },
  CANCELADA: { texto: "Cancelada", clase: "bg-niebla/70 text-acero" },
  CANCELANDO: { texto: "Cancelando…", clase: "bg-niebla/70 text-acero" },
  REQUIERE_ATENCION: { texto: "En revisión", clase: "bg-[#b4553f]/15 text-[#9b4533]" },
};
const EN_PROCESO = { texto: "En proceso", clase: "bg-niebla/70 text-acero" };
const VISIBLES = 5;

const fecha = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

function Reserva({ r, onActualizar, onCancelar, ocupada }) {
  const [confirmando, setConfirmando] = useState(false);
  const e = ESTADOS[r.estado] ?? EN_PROCESO;
  return (
    <li className="py-3 text-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold" title={r.hotel ?? undefined}>
            {nombreCiudad(r.destino)} · {r.hotel}
          </p>
          <p className="mt-0.5 text-xs text-piedra">
            {r.noches != null && `${plural(r.noches, "noche", "noches")} · `}
            {r.personas != null && `${plural(r.personas, "persona", "personas")} · `}
            {r.auto ? "con auto" : "sin auto"}
          </p>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${e.clase}`}>{e.texto}</span>
      </div>
      <div className="mt-1.5 flex items-baseline justify-between gap-2">
        <p className="font-mono text-xs text-piedra">
          {codigoReserva(r.sagaId)}
          {r.creado && <span className="ml-1.5 font-sans">· {fecha.format(new Date(r.creado))}</span>}
        </p>
        {r.total != null && (
          <p className={`font-semibold ${r.estado === "CONFIRMADA" ? "text-oliva-oscuro" : "text-piedra line-through"}`}>
            {pesos(r.total)}
          </p>
        )}
      </div>

      {confirmando ? (
        <div className="mt-2 rounded-lg bg-papel p-2.5" role="alertdialog" aria-label="Confirmar cancelación">
          <p className="text-xs text-acero">
            ¿Cancelar esta reserva? Se liberan {r.auto ? "el auto, el hotel y el vuelo" : "el hotel y el vuelo"}.
          </p>
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => {
                setConfirmando(false);
                onCancelar(r.sagaId);
              }}
              className="rounded-md bg-[#9b4533] px-2.5 py-1 text-xs font-semibold text-papel hover:bg-[#b4553f]"
            >
              Sí, cancelar
            </button>
            <button
              onClick={() => setConfirmando(false)}
              className="rounded-md px-2.5 py-1 text-xs font-medium text-acero hover:bg-white"
            >
              No, mantenerla
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-1.5 flex gap-1">
          <button
            onClick={() => onActualizar(r.sagaId)}
            disabled={ocupada}
            className="rounded-md px-2 py-1 text-xs font-medium text-acero hover:bg-papel hover:text-tinta disabled:opacity-50"
          >
            {ocupada ? "Procesando…" : "Actualizar estado"}
          </button>
          {r.estado === "CONFIRMADA" && (
            <button
              onClick={() => setConfirmando(true)}
              disabled={ocupada}
              className="rounded-md px-2 py-1 text-xs font-medium text-[#9b4533] hover:bg-[#b4553f]/10 disabled:opacity-50"
            >
              Cancelar reserva
            </button>
          )}
        </div>
      )}
    </li>
  );
}

export default function MisReservas({ reservas, error, onActualizar, onCancelar, ocupada }) {
  const [todas, setTodas] = useState(false);
  if (reservas === null) {
    return <section className="pulso h-28 rounded-2xl border border-niebla bg-white/60" aria-busy="true" />;
  }
  return (
    <section className="rounded-2xl border border-niebla bg-white p-5" aria-labelledby="titulo-mis-reservas">
      <h2 id="titulo-mis-reservas" className="scroll-mt-4 font-display text-lg font-semibold">
        Mis reservas
      </h2>
      {error && (
        <p role="alert" className="mt-2 rounded-lg bg-[#b4553f]/10 px-3 py-2 text-xs text-[#9b4533]">
          {error}
        </p>
      )}
      {reservas.length === 0 ? (
        <p className="mt-1 text-sm text-acero">Aún no tienes reservas. Cuando reserves un paquete, aparecerá aquí.</p>
      ) : (
        <>
          <ul className="mt-1 divide-y divide-niebla/70">
            {reservas.slice(0, todas ? undefined : VISIBLES).map((r) => (
              <Reserva
                key={r.sagaId}
                r={r}
                onActualizar={onActualizar}
                onCancelar={onCancelar}
                ocupada={ocupada === r.sagaId}
              />
            ))}
          </ul>
          {reservas.length > VISIBLES && (
            <button
              onClick={() => setTodas((t) => !t)}
              className="mt-2 text-xs font-semibold text-selva underline-offset-2 hover:underline"
            >
              {todas ? "Ver menos" : `Ver las ${reservas.length} reservas`}
            </button>
          )}
        </>
      )}
    </section>
  );
}
