// Resultado de la reserva en lenguaje de cliente. Por debajo es la SAGA del servicio Órdenes:
//   CONFIRMADA         -> vuelo, hotel y auto quedaron reservados
//   COMPENSADA         -> algo falló y lo ya reservado se canceló solo: no queda un viaje a medias
//   REQUIERE_ATENCION  -> no se pudo cancelar todo automáticamente: lo revisa una persona
// El detalle técnico (pasos y compensaciones) solo se ve en modo demo, en PanelSaga.
import { pesos, plural, nombreCiudad } from "../formato";

export const codigoReserva = (sagaId) => `WS-${sagaId.slice(0, 8).toUpperCase()}`;

function Resumen({ reserva }) {
  return (
    <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      <dt className="text-piedra">Destino</dt>
      <dd className="font-medium">{nombreCiudad(reserva.ciudad)}</dd>
      <dt className="text-piedra">Hotel</dt>
      <dd className="truncate font-medium" title={reserva.hotel}>
        {reserva.hotel}
      </dd>
      <dt className="text-piedra">Viajeros</dt>
      <dd className="font-medium">
        {plural(reserva.personas, "persona", "personas")} · {plural(reserva.noches, "noche", "noches")}
      </dd>
      <dt className="text-piedra">Total</dt>
      <dd className="font-display text-lg font-semibold text-oliva-oscuro">{pesos(reserva.total)}</dd>
    </dl>
  );
}

export default function ResultadoReserva({ saga, reserva }) {
  if (!saga) {
    return (
      <section className="rounded-2xl border border-dashed border-pizarra/60 p-5">
        <h2 className="font-display text-lg font-semibold">Tu reserva</h2>
        <p className="mt-1 text-sm text-acero">
          Elige un paquete y resérvalo. Vuelo, hotel y auto se confirman juntos: si alguno no está disponible,
          cancelamos el resto y no te quedas con medio viaje.
        </p>
      </section>
    );
  }

  if (saga.estado === "PENDIENTE") {
    return (
      <section className="entrar rounded-2xl border border-niebla bg-white p-5" aria-live="polite">
        <h2 className="font-display text-lg font-semibold">Confirmando tu viaje…</h2>
        <p className="pulso mt-1 text-sm text-acero">Estamos reservando tu vuelo, tu hotel y tu auto.</p>
      </section>
    );
  }

  if (saga.estado === "CONFIRMADA") {
    return (
      <section className="entrar rounded-2xl border-2 border-musgo bg-white p-5" aria-live="polite">
        <p className="text-xs font-semibold tracking-wider text-selva uppercase">Reserva confirmada</p>
        <h2 className="mt-1 font-display text-xl font-semibold">¡Tu viaje está listo!</h2>
        <p className="mt-1 text-sm text-acero">Vuelo, hotel y auto quedaron reservados.</p>
        <p className="mt-3 inline-block rounded-lg bg-papel px-3 py-1.5 font-mono text-sm font-medium">
          {codigoReserva(saga.sagaId)}
        </p>
        {reserva && <Resumen reserva={reserva} />}
      </section>
    );
  }

  if (saga.estado === "COMPENSADA") {
    return (
      <section className="entrar rounded-2xl border-2 border-mostaza bg-white p-5" aria-live="polite">
        <p className="text-xs font-semibold tracking-wider text-oliva-oscuro uppercase">Reserva no completada</p>
        <h2 className="mt-1 font-display text-xl font-semibold">No pudimos completar tu viaje</h2>
        <p className="mt-2 text-sm text-acero">
          Uno de nuestros proveedores no respondió. Para que no te quedes con medio viaje,{" "}
          <strong className="font-semibold text-tinta">cancelamos automáticamente todo lo que alcanzamos a reservar</strong>
          . Puedes intentarlo de nuevo en unos minutos o elegir otro paquete.
        </p>
        <p className="mt-3 font-mono text-xs text-piedra">Referencia: {codigoReserva(saga.sagaId)}</p>
      </section>
    );
  }

  if (saga.estado === "REQUIERE_ATENCION") {
    return (
      <section className="entrar rounded-2xl border-2 border-[#b4553f] bg-white p-5" aria-live="polite">
        <p className="text-xs font-semibold tracking-wider text-[#9b4533] uppercase">En revisión</p>
        <h2 className="mt-1 font-display text-xl font-semibold">Estamos revisando tu reserva</h2>
        <p className="mt-2 text-sm text-acero">
          Tu viaje no se completó y una parte no se pudo cancelar automáticamente. Nuestro equipo la está revisando.
          Si nos contactas, usa esta referencia:
        </p>
        <p className="mt-3 inline-block rounded-lg bg-papel px-3 py-1.5 font-mono text-sm font-medium">
          {codigoReserva(saga.sagaId)}
        </p>
      </section>
    );
  }

  return (
    <section className="entrar rounded-2xl border border-niebla bg-white p-5" aria-live="polite">
      <h2 className="font-display text-lg font-semibold">No pudimos procesar tu reserva</h2>
      <p className="mt-1 text-sm text-[#9b4533]">{saga.error ?? "Inténtalo de nuevo en unos minutos."}</p>
    </section>
  );
}
