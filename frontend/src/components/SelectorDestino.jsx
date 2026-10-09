// Botón "Selecciona tu destino": abre un panel con TODOS los destinos de la página, con un buscador.
//   - En celular es una hoja a pantalla completa; desde 640 px, un panel desplegable bajo el botón.
//   - Primero los destinos con paquetes WanderSync y después los que solo tienen ofertas de Booking.
//   - Escape o un clic fuera lo cierran; al cerrarse, el foco vuelve al botón.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { normalizar, pesos } from "../formato";
import { CATEGORIAS } from "./TarjetaOferta";

function Fila({ d, activo, onElegir }) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onElegir(d.clave)}
        aria-current={activo ? "true" : undefined}
        className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
          activo ? "bg-selva text-papel" : "hover:bg-papel"
        }`}
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate font-semibold">{d.nombre}</span>
          <span className={`block truncate text-xs ${activo ? "text-niebla" : "text-piedra"}`}>
            {[d.pais, d.codigo].filter(Boolean).join(" · ") || "Destino de Booking"}
          </span>
        </span>
        {d.paquetes ? (
          <span className={`shrink-0 text-right text-xs ${activo ? "text-niebla" : "text-acero"}`}>
            <span className="block font-semibold text-musgo">Paquete</span>
            {d.vueloDesde != null && <span className="block">vuelo desde {pesos(d.vueloDesde)}</span>}
          </span>
        ) : (
          <span className="flex max-w-[45%] shrink-0 flex-wrap justify-end gap-1">
            {[...d.categorias].map((c) => (
              <span
                key={c}
                className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                  activo ? "bg-white/15 text-papel" : "bg-niebla/50 text-acero"
                }`}
              >
                {CATEGORIAS[c]}
              </span>
            ))}
          </span>
        )}
      </button>
    </li>
  );
}

function Grupo({ titulo, lista, seleccion, onElegir }) {
  if (lista.length === 0) return null;
  return (
    <section className="mt-3 first:mt-0">
      <h3 className="sticky top-0 z-10 bg-white px-3 py-1.5 text-[11px] font-semibold tracking-wider text-piedra uppercase">
        {titulo} <span className="font-normal">({lista.length})</span>
      </h3>
      <ul>
        {lista.map((d) => (
          <Fila key={d.clave} d={d} activo={d.clave === seleccion} onElegir={onElegir} />
        ))}
      </ul>
    </section>
  );
}

export default function SelectorDestino({ catalogo, seleccion, onElegir }) {
  const [abierto, setAbierto] = useState(false);
  const [consulta, setConsulta] = useState("");
  const raiz = useRef(null);
  const boton = useRef(null);
  const entrada = useRef(null);
  const idPanel = useId();
  const elegido = catalogo.porClave.get(seleccion);

  const cerrar = (devolverFoco = true) => {
    setAbierto(false);
    setConsulta("");
    if (devolverFoco) boton.current?.focus();
  };

  useEffect(() => {
    if (!abierto) return;
    entrada.current?.focus();
    const fuera = (e) => raiz.current && !raiz.current.contains(e.target) && cerrar(false);
    const tecla = (e) => e.key === "Escape" && cerrar();
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", tecla);
    // En celular el panel ocupa la pantalla: se bloquea el scroll de la página de atrás
    const movil = window.matchMedia("(max-width: 639px)").matches;
    if (movil) document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("keydown", tecla);
      document.body.style.overflow = "";
    };
  }, [abierto]);

  const filtro = (d) => {
    const q = normalizar(consulta);
    return !q || [d.nombre, d.pais, d.codigo].some((t) => t && normalizar(t).includes(q));
  };
  const conPaquetes = useMemo(() => catalogo.conPaquetes.filter(filtro), [catalogo, consulta]); // eslint-disable-line react-hooks/exhaustive-deps
  const soloOfertas = useMemo(() => catalogo.soloOfertas.filter(filtro), [catalogo, consulta]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={raiz} className="relative">
      <button
        ref={boton}
        type="button"
        onClick={() => (abierto ? cerrar() : setAbierto(true))}
        aria-haspopup="dialog"
        aria-expanded={abierto}
        aria-controls={idPanel}
        className="flex w-full items-center gap-3 rounded-xl border border-niebla bg-white px-4 py-3 text-left transition hover:border-pizarra"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" className="size-5 shrink-0 fill-none stroke-selva stroke-2">
          <path d="M12 21s-7-6.1-7-11.5a7 7 0 0 1 14 0C19 14.9 12 21 12 21Z" />
          <circle cx="12" cy="9.5" r="2.5" />
        </svg>
        <span className="min-w-0 flex-1">
          {elegido ? (
            <>
              <span className="block truncate font-semibold">{elegido.nombre}</span>
              <span className="block truncate text-xs text-piedra">
                {elegido.paquetes ? "Con paquetes WanderSync" : "Ofertas de Booking"}
                {elegido.pais ? ` · ${elegido.pais}` : ""}
              </span>
            </>
          ) : (
            <span className="block font-semibold text-acero">Selecciona tu destino</span>
          )}
        </span>
        <span className="shrink-0 text-xs font-medium text-selva">{elegido ? "Cambiar" : "Ver todos"}</span>
        <svg
          viewBox="0 0 20 20"
          aria-hidden="true"
          className={`size-4 shrink-0 fill-acero transition ${abierto ? "rotate-180" : ""}`}
        >
          <path d="M5.3 7.3a1 1 0 0 1 1.4 0L10 10.6l3.3-3.3a1 1 0 1 1 1.4 1.4l-4 4a1 1 0 0 1-1.4 0l-4-4a1 1 0 0 1 0-1.4Z" />
        </svg>
      </button>

      {abierto && (
        <div
          id={idPanel}
          role="dialog"
          aria-label="Elige tu destino"
          className="fixed inset-0 z-50 flex flex-col bg-white text-tinta sm:absolute sm:inset-auto sm:top-full sm:left-0 sm:mt-2 sm:w-full sm:max-w-xl sm:max-h-[min(28rem,70vh)] sm:rounded-2xl sm:border sm:border-niebla sm:shadow-2xl sm:shadow-black/25"
        >
          <div className="flex items-center gap-2 border-b border-niebla p-3">
            <label htmlFor={`${idPanel}-q`} className="sr-only">
              Buscar destino
            </label>
            <input
              ref={entrada}
              id={`${idPanel}-q`}
              type="search"
              value={consulta}
              onChange={(e) => setConsulta(e.target.value)}
              placeholder="Busca una ciudad o un país"
              autoComplete="off"
              className="min-w-0 flex-1 rounded-lg border border-niebla bg-papel px-3 py-2.5 text-base outline-none focus:border-selva sm:text-sm"
            />
            <button
              type="button"
              onClick={() => cerrar()}
              className="shrink-0 rounded-lg px-3 py-2.5 text-sm font-medium text-acero hover:bg-papel sm:hidden"
            >
              Cerrar
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2">
            <Grupo
              titulo="Con paquetes WanderSync"
              lista={conPaquetes}
              seleccion={seleccion}
              onElegir={(c) => {
                onElegir(c);
                cerrar();
              }}
            />
            <Grupo
              titulo="Más destinos · ofertas de Booking"
              lista={soloOfertas}
              seleccion={seleccion}
              onElegir={(c) => {
                onElegir(c);
                cerrar();
              }}
            />
            {conPaquetes.length + soloOfertas.length === 0 && (
              <p className="px-3 py-6 text-center text-sm text-acero">No encontramos "{consulta}".</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
