import { useEffect, useMemo, useRef, useState } from "react";
import { gql } from "./api";
import { CERRAR_SESION, ORDEN, PAQUETES, RESERVAR, YO } from "./operaciones";
import { DEMO, nombreCiudad, plural } from "./formato";
import Encabezado from "./components/Encabezado";
import Buscador from "./components/Buscador";
import TarjetaPaquete from "./components/TarjetaPaquete";
import ResultadoReserva from "./components/ResultadoReserva";
import Historial from "./components/Historial";
import DialogoAcceso from "./components/DialogoAcceso";
// Herramientas de la sustentación: solo se muestran en modo demo (?demo)
import PanelSaga from "./components/PanelSaga";
import Inspector from "./components/Inspector";

const POR_PAGINA = 10;

export default function App() {
  const [usuario, setUsuario] = useState(null);
  const [acceso, setAcceso] = useState(null); // null | { modo: "entrar" | "registro", motivo?: string }
  const [pendiente, setPendiente] = useState(null); // paquete que se quiso reservar sin sesión

  const [destino, setDestino] = useState("MDE");
  const [noches, setNoches] = useState(3);
  const [personas, setPersonas] = useState(2);
  const [buscado, setBuscado] = useState(null); // { destino, noches, personas } de la última búsqueda
  const [paquetes, setPaquetes] = useState([]);
  const [cargando, setCargando] = useState(false);
  const [errorBusqueda, setErrorBusqueda] = useState("");

  const [orden, setOrden] = useState("precio");
  const [visibles, setVisibles] = useState(POR_PAGINA);

  const [saga, setSaga] = useState(null);
  const [reservandoClave, setReservandoClave] = useState(null);
  const [reservas, setReservas] = useState([]);
  const refReserva = useRef(null);

  // En pantallas angostas el resultado de la reserva queda debajo de los paquetes: al reservar se lleva a la vista
  useEffect(() => {
    if (saga && window.matchMedia("(max-width: 1023px)").matches) {
      refReserva.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [saga?.estado]);

  // ¿Ya hay sesión? (la cookie HttpOnly viaja sola; el Gateway responde quién es el usuario)
  useEffect(() => {
    gql(YO)
      .then((d) => setUsuario(d.yo))
      .catch(() => {});
    buscar("MDE", 3, 2);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function buscar(d = destino, n = noches, p = personas) {
    setCargando(true);
    setErrorBusqueda("");
    try {
      const data = await gql(PAQUETES, { destino: d, noches: n, personas: p });
      setPaquetes(data.paquetes);
      setBuscado({ destino: d, noches: n, personas: p });
      setVisibles(POR_PAGINA);
    } catch (e) {
      setErrorBusqueda(e.message);
      setPaquetes([]);
    } finally {
      setCargando(false);
    }
  }

  const lista = useMemo(
    () =>
      [...paquetes].sort((a, b) =>
        orden === "rating" ? (b.hotel.rating ?? -1) - (a.hotel.rating ?? -1) : a.precioTotal - b.precioTotal,
      ),
    [paquetes, orden],
  );

  // Datos de la reserva para mostrarle al cliente el resumen (el Gateway solo devuelve id y estado)
  const [ultimaReserva, setUltimaReserva] = useState(null);

  async function reservar(p) {
    if (!usuario) {
      setPendiente(p);
      setAcceso({ modo: "registro", motivo: "Crea tu cuenta (o inicia sesión) para terminar tu reserva." });
      return;
    }
    const clave = `${p.vuelo.id}-${p.hotel.id}-${p.auto.id}`;
    const datos = {
      ciudad: p.vuelo.destino,
      hotel: p.hotel.nombre,
      personas: buscado.personas,
      noches: buscado.noches,
      total: p.precioTotal,
    };
    setReservandoClave(clave);
    setUltimaReserva(datos);
    setSaga({ estado: "PENDIENTE" });
    try {
      // 1) La mutation dispara la SAGA en el orquestador (Órdenes) y espera su resultado final
      const { reservarPaquete } = await gql(RESERVAR, {
        vueloId: p.vuelo.id,
        hotelId: p.hotel.id,
        autoId: p.auto.id,
        personas: buscado.personas,
      });
      // 2) Se consulta el detalle (último paso registrado en la bitácora de la SAGA)
      const { orden: detalle } = await gql(ORDEN, { sagaId: reservarPaquete.sagaId });
      const final = detalle ?? reservarPaquete;
      setSaga(final);
      setReservas((r) => [{ sagaId: final.sagaId, estado: final.estado, ...datos }, ...r]);
    } catch (e) {
      if (/iniciar sesión/i.test(e.message)) {
        // La sesión expiró (dura 1 hora): se pide iniciar de nuevo y la reserva se retoma
        setUsuario(null);
        setPendiente(p);
        setAcceso({ modo: "entrar", motivo: "Tu sesión expiró. Entra de nuevo para terminar tu reserva." });
        setSaga(null);
      } else {
        setSaga({ estado: "ERROR", error: e.message });
      }
    } finally {
      setReservandoClave(null);
    }
  }

  async function consultar(sagaId) {
    try {
      const { orden: detalle } = await gql(ORDEN, { sagaId });
      if (detalle) {
        setSaga(detalle);
        const r = reservas.find((x) => x.sagaId === sagaId);
        if (r) setUltimaReserva(r);
        setReservas((rs) => rs.map((x) => (x.sagaId === sagaId ? { ...x, estado: detalle.estado } : x)));
      }
    } catch (e) {
      setSaga({ estado: "ERROR", sagaId, error: e.message });
    }
  }

  async function salir() {
    try {
      await gql(CERRAR_SESION);
    } finally {
      setUsuario(null);
    }
  }

  function alIniciarSesion(u) {
    setUsuario(u);
    setAcceso(null);
  }

  // Si el usuario quiso reservar sin sesión, la reserva se retoma apenas entra.
  // (Se hace en un efecto porque reservar() necesita leer el "usuario" ya actualizado.)
  useEffect(() => {
    if (usuario && pendiente && !acceso) {
      const p = pendiente;
      setPendiente(null);
      reservar(p);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usuario]);

  return (
    <div className="min-h-screen">
      <Encabezado
        usuario={usuario}
        onEntrar={() => setAcceso({ modo: "entrar" })}
        onRegistrar={() => setAcceso({ modo: "registro" })}
        onSalir={salir}
      />
      <Buscador
        destino={destino}
        noches={noches}
        personas={personas}
        onDestino={setDestino}
        onNoches={setNoches}
        onPersonas={setPersonas}
        onBuscar={() => buscar()}
        cargando={cargando}
      />

      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section aria-labelledby="titulo-resultados">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="titulo-resultados" className="font-display text-2xl font-semibold tracking-tight">
                {buscado ? `Paquetes a ${nombreCiudad(buscado.destino)}` : "Paquetes"}
              </h2>
              {buscado && !cargando && (
                <p className="text-sm text-acero">
                  {plural(lista.length, "opción", "opciones")} · {plural(buscado.noches, "noche", "noches")} ·{" "}
                  {plural(buscado.personas, "persona", "personas")}
                </p>
              )}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <span className="text-acero">Ordenar</span>
              <select
                value={orden}
                onChange={(e) => setOrden(e.target.value)}
                className="rounded-lg border border-niebla bg-white px-2.5 py-1.5"
              >
                <option value="precio">Menor precio</option>
                <option value="rating">Mejor calificación</option>
              </select>
            </label>
          </div>

          <div className="mt-4 space-y-3">
            {cargando &&
              Array.from({ length: 3 }, (_, i) => (
                <div key={i} className="pulso h-32 rounded-2xl border border-niebla bg-white/60" />
              ))}

            {!cargando && errorBusqueda && (
              <p role="alert" className="rounded-2xl bg-[#b4553f]/10 p-5 text-[#9b4533]">
                {errorBusqueda}
              </p>
            )}

            {!cargando && !errorBusqueda && buscado && lista.length === 0 && (
              <p className="rounded-2xl border border-dashed border-pizarra/60 p-6 text-acero">
                {DEMO
                  ? "No hay paquetes para este destino todavía. Si la ingesta no ha corrido, lánzala desde el panel de Prefect."
                  : "No encontramos paquetes para este destino en este momento. Prueba con otra ciudad."}
              </p>
            )}

            {!cargando &&
              lista.slice(0, visibles).map((p) => {
                const clave = `${p.vuelo.id}-${p.hotel.id}-${p.auto.id}`;
                return (
                  <TarjetaPaquete
                    key={clave}
                    paquete={p}
                    noches={buscado.noches}
                    personas={buscado.personas}
                    onReservar={reservar}
                    reservando={reservandoClave === clave}
                    deshabilitado={reservandoClave !== null}
                  />
                );
              })}

            {!cargando && lista.length > visibles && (
              <button
                onClick={() => setVisibles((v) => v + POR_PAGINA)}
                className="w-full rounded-2xl border border-niebla py-3 text-sm font-semibold text-acero transition hover:bg-white"
              >
                Ver {Math.min(POR_PAGINA, lista.length - visibles)} más
              </button>
            )}
          </div>
        </section>

        <aside ref={refReserva} className="scroll-mt-4 space-y-4 lg:sticky lg:top-4 lg:self-start">
          <ResultadoReserva saga={saga} reserva={ultimaReserva} />
          <Historial reservas={reservas} onConsultar={consultar} />
          {DEMO && (
            <>
              <PanelSaga saga={saga} />
              <Inspector />
            </>
          )}
        </aside>
      </main>

      <footer className="border-t border-niebla">
        <p className="mx-auto max-w-6xl px-4 py-6 text-xs text-piedra sm:px-6">
          {DEMO
            ? "WanderSync · Parcial 2, Patrones Arquitectónicos Avanzados · Docker Compose, GraphQL, SAGA, Dask y Prefect · modo demo"
            : "WanderSync · Vuelo, hotel y auto en una sola reserva"}
        </p>
      </footer>

      <DialogoAcceso
        abierto={acceso !== null}
        modoInicial={acceso?.modo}
        motivo={acceso?.motivo}
        onCerrar={() => {
          setAcceso(null);
          setPendiente(null);
        }}
        onSesion={alIniciarSesion}
      />
    </div>
  );
}
