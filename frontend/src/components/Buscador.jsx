// Portada + formulario de búsqueda: destino, número de noches y número de personas.
import { DESTINOS } from "../formato";

// Selector numérico con botones − y + (noches, personas)
function Contador({ id, etiqueta, valor, min, max, onCambio, singular, plural }) {
  const fijar = (n) => onCambio(Math.min(max, Math.max(min, n)));
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-xs font-semibold tracking-wide text-acero uppercase">
        {etiqueta}
      </label>
      <div className="flex items-center rounded-xl border border-niebla bg-white">
        <button
          type="button"
          aria-label={`Una ${singular} menos`}
          onClick={() => fijar(valor - 1)}
          disabled={valor <= min}
          className="px-3.5 py-2.5 text-lg text-acero hover:text-tinta disabled:opacity-30"
        >
          −
        </button>
        <input
          id={id}
          type="number"
          min={min}
          max={max}
          value={valor}
          onChange={(e) => fijar(Number(e.target.value) || min)}
          aria-describedby={`${id}-unidad`}
          className="w-8 [appearance:textfield] bg-transparent text-center font-semibold [&::-webkit-inner-spin-button]:appearance-none"
        />
        <span id={`${id}-unidad`} className="pr-1 text-sm text-acero">
          {valor === 1 ? singular : plural}
        </span>
        <button
          type="button"
          aria-label={`Una ${singular} más`}
          onClick={() => fijar(valor + 1)}
          disabled={valor >= max}
          className="px-3.5 py-2.5 text-lg text-acero hover:text-tinta disabled:opacity-30"
        >
          +
        </button>
      </div>
    </div>
  );
}

export default function Buscador({ destino, noches, personas, onDestino, onNoches, onPersonas, onBuscar, cargando }) {
  return (
    <section className="topo bg-noche text-papel">
      <div className="mx-auto max-w-6xl px-4 pt-8 pb-12 sm:px-6 sm:pt-12 sm:pb-16">
        <p className="font-mono text-xs tracking-[0.2em] text-musgo uppercase">Paquetes de viaje · Colombia</p>
        <h1 className="mt-3 max-w-2xl font-display text-4xl leading-[1.05] font-semibold tracking-tight sm:text-6xl">
          Vuelo, hotel y auto.
          <span className="block text-mostaza italic">Todo o nada.</span>
        </h1>
        <p className="mt-4 max-w-xl text-niebla">
          Reservas tu viaje completo en un solo paso. Si alguna parte no se puede confirmar, cancelamos el resto
          automáticamente: nunca te quedas con medio viaje.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            onBuscar();
          }}
          className="mt-8 grid gap-4 rounded-2xl bg-papel p-4 text-tinta shadow-xl shadow-black/20 sm:grid-cols-[auto_auto_1fr] sm:items-end sm:p-5 lg:grid-cols-[1fr_auto_auto_auto]"
        >
          <fieldset className="sm:col-span-3 lg:col-span-1">
            <legend className="mb-2 text-xs font-semibold tracking-wide text-acero uppercase">Destino</legend>
            <div className="grid grid-cols-3 gap-2">
              {DESTINOS.map((d) => {
                const activo = d.codigo === destino;
                return (
                  <label
                    key={d.codigo}
                    className={`cursor-pointer rounded-xl border px-2.5 py-2.5 transition sm:px-3 ${
                      activo ? "border-selva bg-selva text-papel" : "border-niebla bg-white hover:border-pizarra"
                    }`}
                  >
                    <input
                      type="radio"
                      name="destino"
                      value={d.codigo}
                      checked={activo}
                      onChange={() => onDestino(d.codigo)}
                      className="sr-only"
                    />
                    <span className="block font-mono text-xs opacity-70">{d.codigo}</span>
                    <span className="block text-sm leading-tight font-semibold sm:text-base">{d.nombre}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <Contador
            id="noches"
            etiqueta="Noches"
            valor={noches}
            min={1}
            max={30}
            onCambio={onNoches}
            singular="noche"
            plural="noches"
          />
          <Contador
            id="personas"
            etiqueta="Personas"
            valor={personas}
            min={1}
            max={9}
            onCambio={onPersonas}
            singular="persona"
            plural="personas"
          />

          <button
            type="submit"
            disabled={cargando}
            className="rounded-xl bg-mostaza px-6 py-3 font-semibold text-noche transition hover:bg-[#bda55a] disabled:opacity-60"
          >
            {cargando ? "Buscando…" : "Buscar paquetes"}
          </button>
        </form>
      </div>
    </section>
  );
}
