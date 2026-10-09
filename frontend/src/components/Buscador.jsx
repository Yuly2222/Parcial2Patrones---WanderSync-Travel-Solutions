// Portada + formulario de búsqueda:
//   1. "Selecciona tu destino": TODOS los destinos de la página (con paquetes o solo con ofertas de Booking)
//   2. "Búsqueda por paquetes": accesos directos a los destinos que tienen paquete WanderSync
//   3. Noches, personas y buscar
import SelectorDestino from "./SelectorDestino";

// Selector numérico con botones − y + (noches, personas)
function Contador({ id, etiqueta, valor, min, max, onCambio, singular, plural }) {
  const fijar = (n) => onCambio(Math.min(max, Math.max(min, n)));
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-xs font-semibold tracking-wide text-acero uppercase">
        {etiqueta}
      </label>
      <div className="flex items-center justify-between rounded-xl border border-niebla bg-white">
        <button
          type="button"
          aria-label={`Una ${singular} menos`}
          onClick={() => fijar(valor - 1)}
          disabled={valor <= min}
          className="px-3 py-2.5 text-lg text-acero hover:text-tinta disabled:opacity-30 sm:px-3.5"
        >
          −
        </button>
        <span className="flex items-baseline justify-center">
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
          <span id={`${id}-unidad`} className="sr-only pr-1 text-sm text-acero min-[400px]:not-sr-only">
            {valor === 1 ? singular : plural}
          </span>
        </span>
        <button
          type="button"
          aria-label={`Una ${singular} más`}
          onClick={() => fijar(valor + 1)}
          disabled={valor >= max}
          className="px-3 py-2.5 text-lg text-acero hover:text-tinta disabled:opacity-30 sm:px-3.5"
        >
          +
        </button>
      </div>
    </div>
  );
}

export default function Buscador({
  catalogo,
  destino,
  noches,
  personas,
  onDestino,
  onNoches,
  onPersonas,
  onBuscar,
  cargando,
}) {
  const elegido = catalogo.porClave.get(destino);
  const soloOfertas = elegido && !elegido.paquetes;
  return (
    <section className="topo bg-noche text-papel">
      <div className="mx-auto max-w-6xl px-4 pt-8 pb-12 sm:px-6 sm:pt-12 sm:pb-16">
        <p className="font-mono text-xs tracking-[0.2em] text-musgo uppercase">Paquetes de viaje · desde Bogotá</p>
        <h1 className="mt-3 max-w-2xl font-display text-[2.5rem] leading-[1.05] font-semibold tracking-tight sm:text-6xl">
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
          className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-5 rounded-2xl bg-papel p-4 text-tinta shadow-xl shadow-black/20 sm:p-5"
        >
          <div>
            <p className="mb-2 text-xs font-semibold tracking-wide text-acero uppercase">Destino</p>
            <SelectorDestino catalogo={catalogo} seleccion={destino} onElegir={onDestino} />
          </div>

          {catalogo.conPaquetes.length > 0 && (
            // div con role="group" y no <fieldset>: un fieldset no deja que su contenido se desplace de lado
            <div role="group" aria-labelledby="titulo-por-paquetes" className="min-w-0">
              <p id="titulo-por-paquetes" className="mb-2 text-xs font-semibold tracking-wide text-acero uppercase">
                Búsqueda por paquetes
              </p>
              {/* Celular: una fila que se desliza de lado. Desde 640 px: los botones bajan de línea */}
              <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0">
                {catalogo.conPaquetes.map((d) => {
                  const activo = d.clave === destino;
                  return (
                    <label
                      key={d.clave}
                      className={`relative shrink-0 cursor-pointer rounded-xl border px-3 py-2 transition ${
                        activo ? "border-selva bg-selva text-papel" : "border-niebla bg-white hover:border-pizarra"
                      }`}
                    >
                      <input
                        type="radio"
                        name="destino"
                        value={d.clave}
                        checked={activo}
                        onChange={() => onDestino(d.clave)}
                        className="sr-only"
                      />
                      <span className="block font-mono text-[10px] opacity-70">{d.codigo}</span>
                      <span className="block text-sm leading-tight font-semibold whitespace-nowrap">{d.nombre}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-[minmax(0,13rem)_minmax(0,13rem)_1fr] sm:items-end sm:gap-4">
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
              className="col-span-2 rounded-xl bg-mostaza px-6 py-3 font-semibold text-noche transition hover:bg-[#bda55a] disabled:opacity-60 sm:col-span-1"
            >
              {cargando ? "Buscando…" : soloOfertas ? "Ver ofertas" : "Buscar paquetes"}
            </button>
          </div>
          {soloOfertas && (
            <p className="-mt-2 text-xs text-acero">
              Aún no tenemos paquetes a {elegido.nombre}: te mostramos las ofertas de Booking para ese destino.
            </p>
          )}
        </form>
      </div>
    </section>
  );
}
