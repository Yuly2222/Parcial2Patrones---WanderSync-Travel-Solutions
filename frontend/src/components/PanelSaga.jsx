// Línea de tiempo de la SAGA de la última reserva: pasos hacia adelante y compensaciones en orden inverso.
// Es la evidencia visual de la demo (d): con FORZAR_FALLO_AUTOS=true se ve cómo hotel y vuelo se cancelan solos.
import { lineaDeTiempo, PASOS } from "../formato";

const NOMBRE = { vuelos: "Vuelo", hoteles: "Hotel", autos: "Auto" };

const ESTILO_PASO = {
  ok: { punto: "bg-musgo border-musgo", texto: "Confirmado", color: "text-selva" },
  revertido: { punto: "bg-mostaza border-mostaza", texto: "Reservado → cancelado", color: "text-oliva-oscuro" },
  error: { punto: "bg-[#b4553f] border-[#b4553f]", texto: "Falló", color: "text-[#9b4533]" },
  omitido: { punto: "bg-white border-niebla", texto: "No se ejecutó", color: "text-piedra" },
  pendiente: { punto: "bg-niebla border-niebla pulso", texto: "En curso…", color: "text-acero" },
};

const ESTADO_SAGA = {
  CONFIRMADA: { texto: "Confirmada", clase: "bg-musgo/25 text-selva" },
  COMPENSADA: { texto: "Compensada", clase: "bg-mostaza/25 text-oliva-oscuro" },
  REQUIERE_ATENCION: { texto: "Requiere atención", clase: "bg-[#b4553f]/15 text-[#9b4533]" },
  EN_CURSO: { texto: "En curso", clase: "bg-niebla/60 text-acero" },
  COMPENSANDO: { texto: "Compensando", clase: "bg-niebla/60 text-acero" },
  CANCELANDO: { texto: "Cancelando", clase: "bg-niebla/60 text-acero" },
  CANCELADA: { texto: "Cancelada por el cliente", clase: "bg-niebla/60 text-acero" },
};

export default function PanelSaga({ saga }) {
  if (!saga) {
    return (
      <section className="rounded-2xl border border-dashed border-pizarra/60 p-5">
        <h2 className="font-display text-lg font-semibold">Transacción SAGA</h2>
        <p className="mt-1 text-sm text-acero">
          Reserva un paquete para ver, paso a paso, cómo el orquestador confirma o compensa cada servicio.
        </p>
        <ol className="mt-4 flex gap-2 font-mono text-xs text-piedra">
          {PASOS.map((p, i) => (
            <li key={p}>
              {i > 0 && <span className="mr-2">→</span>}
              {p}
            </li>
          ))}
        </ol>
      </section>
    );
  }

  const enCurso = saga.estado === "PENDIENTE";
  const { pasos, compensaciones } = lineaDeTiempo(enCurso ? "EN_CURSO" : saga.estado, saga.paso, saga.auto !== null);
  const insignia = ESTADO_SAGA[saga.estado] ?? { texto: "Enviando…", clase: "bg-niebla/60 text-acero pulso" };

  return (
    <section className="entrar rounded-2xl border border-niebla bg-white p-5" aria-live="polite">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold">Transacción SAGA</h2>
          {saga.sagaId && (
            <p className="mt-0.5 font-mono text-[11px] break-all text-piedra" title="saga_id: llave de idempotencia">
              {saga.sagaId}
            </p>
          )}
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${insignia.clase}`}>
          {insignia.texto}
        </span>
      </div>

      <p className="mt-4 text-[11px] font-semibold tracking-wider text-piedra uppercase">Acciones</p>
      <ol className="mt-2 space-y-0">
        {pasos.map((p, i) => {
          const e = ESTILO_PASO[p.estado];
          return (
            <li key={p.servicio} className="relative flex gap-3 pb-3 last:pb-0">
              {i < pasos.length - 1 && (
                <span className="absolute top-4 left-[5px] h-full w-px bg-niebla" aria-hidden="true" />
              )}
              <span className={`relative mt-1 size-[11px] shrink-0 rounded-full border-2 ${e.punto}`} />
              <div className="flex flex-1 items-baseline justify-between gap-2 text-sm">
                <span className="font-medium">
                  {i + 1}. Reservar {NOMBRE[p.servicio].toLowerCase()}
                </span>
                <span className={`text-xs ${e.color}`}>{e.texto}</span>
              </div>
            </li>
          );
        })}
      </ol>

      {compensaciones.length > 0 && (
        <>
          <p className="mt-5 text-[11px] font-semibold tracking-wider text-piedra uppercase">
            Compensaciones · orden inverso
          </p>
          <ol className="mt-2 space-y-1.5">
            {compensaciones.map((c) => (
              <li key={c.servicio} className="flex items-baseline justify-between gap-2 text-sm">
                <span className="font-mono text-xs text-acero">
                  POST /{c.servicio}/reservas/…/cancelar
                </span>
                <span className={`text-xs font-medium ${c.ok ? "text-oliva-oscuro" : "text-[#9b4533]"}`}>
                  {c.ok ? "Cancelada" : "Sin cancelar"}
                </span>
              </li>
            ))}
          </ol>
        </>
      )}

      {saga.paso && (
        <p className="mt-4 rounded-lg bg-papel px-3 py-2 font-mono text-xs text-acero">
          <span className="text-piedra">paso:</span> {saga.paso}
        </p>
      )}
      {saga.error && <p className="mt-4 text-sm text-[#9b4533]">{saga.error}</p>}
    </section>
  );
}
