import { useEffect, useMemo, useRef, useState } from "react";
import { gql } from "./api";
import {
  CANCELAR_RESERVA,
  CERRAR_SESION,
  DESTINOS_DISPONIBLES,
  MIS_RESERVAS,
  OFERTAS,
  ORDEN,
  PAQUETES,
  RESERVAR,
  YO,
} from "./operaciones";
import { DEMO, nombreCiudad, plural, registrarNombres } from "./formato";
import { claveDe as claveDestino, construirCatalogo } from "./destinos";
import TarjetaOferta from "./components/TarjetaOferta";
import Encabezado from "./components/Encabezado";
import Buscador from "./components/Buscador";
import TarjetaPaquete from "./components/TarjetaPaquete";
import ResultadoReserva from "./components/ResultadoReserva";
import Ofertas from "./components/Ofertas";
import MisReservas from "./components/MisReservas";
import PantallaAcceso from "./components/PantallaAcceso";
// Herramientas de la sustentación: solo se muestran en modo demo (?demo)
import PanelSaga from "./components/PanelSaga";
import Inspector from "./components/Inspector";

const POR_PAGINA = 10;

// Resultado de buscar un destino que todavía no tiene paquetes: sus ofertas de Booking, de todas las categorías
function ResultadosOfertas({ destino, ofertas }) {
  return (
    <>
      <h2 id="titulo-resultados" className="font-display text-2xl font-semibold tracking-tight">
        Ofertas para {destino?.nombre ?? "este destino"}
      </h2>
      <p className="mt-1 text-sm text-acero">
        Aún no tenemos paquetes WanderSync a este destino. Estas son las ofertas de Booking.com que encontramos.
      </p>
      {ofertas.length === 0 ? (
        <p className="mt-4 rounded-2xl border border-dashed border-pizarra/60 p-6 text-acero">
          No hay ofertas para este destino en este momento.
        </p>
      ) : (
        <ul className="mt-4 grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 xl:grid-cols-3">
          {ofertas.map((o, i) => (
            <TarjetaOferta key={`${o.categoria}-${i}`} oferta={o} conPaquetes={false} mostrarCategoria />
          ))}
        </ul>
      )}
    </>
  );
}

export default function App() {
  // undefined = todavía no sabemos si hay sesión; null = sin sesión (se muestra la pantalla de acceso)
  const [usuario, setUsuario] = useState(undefined);
  const [avisoAcceso, setAvisoAcceso] = useState("");
  const [pendiente, setPendiente] = useState(null); // paquete que se estaba reservando cuando expiró la sesión

  const [destino, setDestino] = useState("MDE");
  const [noches, setNoches] = useState(3);
  const [personas, setPersonas] = useState(2);
  const [buscado, setBuscado] = useState(null); // { destino, noches, personas, tipo } de la última búsqueda
  const [paquetes, setPaquetes] = useState([]);
  const [cargando, setCargando] = useState(false);
  const [errorBusqueda, setErrorBusqueda] = useState("");

  const [orden, setOrden] = useState("precio");
  const [visibles, setVisibles] = useState(POR_PAGINA);

  const [destinos, setDestinos] = useState(null); // ciudades con paquetes (query destinos)
  const [ofertas, setOfertas] = useState(null); // ofertas de Booking (sección Ofertas y selector de destino)

  // Todos los destinos de la página: con paquetes + los que solo tienen ofertas de Booking
  const catalogo = useMemo(() => construirCatalogo(destinos, ofertas), [destinos, ofertas]);
  const conPaquetes = useMemo(() => new Set((destinos ?? []).map((d) => d.codigo)), [destinos]);

  const [saga, setSaga] = useState(null); // reserva que se muestra en "Tu reserva"
  const [reservandoClave, setReservandoClave] = useState(null);
  const [reservas, setReservas] = useState(null); // "Mis reservas" (null = cargando)
  const [errorReservas, setErrorReservas] = useState("");
  const [ocupada, setOcupada] = useState(null); // sagaId que se está actualizando o cancelando
  const refReserva = useRef(null);
  const refResultados = useRef(null);

  // Desde una oferta de Booking de una ciudad con paquetes: buscar los paquetes de esa ciudad y llevarlos a la vista
  function verPaquetesDe(ciudad) {
    setDestino(ciudad);
    buscar(ciudad, noches, personas);
    refResultados.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  // En pantallas angostas el resultado de la reserva queda debajo de los paquetes: al reservar se lleva a la vista
  useEffect(() => {
    if (saga && window.matchMedia("(max-width: 1023px)").matches) {
      refReserva.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  }, [saga?.estado]);

  // ¿Ya hay sesión? (la cookie HttpOnly viaja sola; el Gateway responde quién es el usuario)
  useEffect(() => {
    gql(YO)
      .then((d) => setUsuario(d.yo))
      .catch(() => setUsuario(null));
    gql(DESTINOS_DISPONIBLES)
      .then((d) => {
        registrarNombres(d.destinos);
        setDestinos(d.destinos);
      })
      .catch(() => setDestinos(null));
    gql(OFERTAS)
      .then((d) => setOfertas(d.ofertas))
      .catch(() => setOfertas([]));
    buscar("MDE", 3, 2);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ¿Ese destino tiene paquetes? Si la lista aún no llega, se intenta con paquetes (los códigos IATA)
  const tienePaquetes = (d) => (destinos === null ? !d.startsWith("n:") : conPaquetes.has(d));

  async function buscar(d = destino, n = noches, p = personas) {
    if (!tienePaquetes(d)) {
      // Destino sin paquetes: se muestran sus ofertas de Booking (ya están cargadas, no hay que pedir nada)
      setBuscado({ destino: d, noches: n, personas: p, tipo: "ofertas" });
      setPaquetes([]);
      setErrorBusqueda("");
      return;
    }
    setCargando(true);
    setErrorBusqueda("");
    try {
      const data = await gql(PAQUETES, { destino: d, noches: n, personas: p });
      setPaquetes(data.paquetes);
      setBuscado({ destino: d, noches: n, personas: p, tipo: "paquetes" });
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

  // "Mis reservas" vienen del servidor (servicio Órdenes): siguen ahí al recargar o al entrar desde otro equipo
  async function cargarReservas() {
    try {
      const { misReservas } = await gql(MIS_RESERVAS);
      setReservas(misReservas);
      setErrorReservas("");
    } catch (e) {
      setReservas((r) => r ?? []);
      setErrorReservas(e.message);
    }
  }

  // Reemplaza una reserva en la lista (y en "Tu reserva" si es la que se está mostrando)
  function actualizarReserva(detalle) {
    setReservas((rs) => {
      const lista = rs ?? [];
      return lista.some((x) => x.sagaId === detalle.sagaId)
        ? lista.map((x) => (x.sagaId === detalle.sagaId ? detalle : x))
        : [detalle, ...lista];
    });
    setSaga((s) => (s?.sagaId === detalle.sagaId ? detalle : s));
  }

  const claveDe = (p) => `${p.vuelo.id}-${p.hotel.id}-${p.auto?.id ?? "sin-auto"}`;

  async function reservar(p) {
    setReservandoClave(claveDe(p));
    setSaga({ estado: "PENDIENTE" });
    try {
      // 1) La mutation dispara la SAGA en el orquestador (Órdenes) y espera su resultado final.
      //    Solo viajan ids, personas y noches: el precio lo calcula el Gateway.
      const { reservarPaquete } = await gql(RESERVAR, {
        vueloId: p.vuelo.id,
        hotelId: p.hotel.id,
        autoId: p.auto?.id ?? null,
        personas: buscado.personas,
        noches: buscado.noches,
      });
      // 2) Se consulta el detalle (último paso de la SAGA + resumen de lo reservado)
      const { orden: detalle } = await gql(ORDEN, {
        sagaId: reservarPaquete.sagaId,
      });
      const final = detalle ?? reservarPaquete;
      setSaga(final);
      if (detalle) actualizarReserva(detalle);
    } catch (e) {
      if (/iniciar sesión/i.test(e.message)) {
        // La sesión expiró (dura 1 hora): vuelve la pantalla de acceso y, al entrar, la reserva se retoma
        setPendiente(p);
        setAvisoAcceso("Tu sesión expiró. Entra de nuevo y terminamos tu reserva.");
        setSaga(null);
        setUsuario(null);
      } else {
        setSaga({ estado: "ERROR", error: e.message });
      }
    } finally {
      setReservandoClave(null);
    }
  }

  async function consultar(sagaId) {
    setOcupada(sagaId);
    try {
      const { orden: detalle } = await gql(ORDEN, { sagaId });
      if (detalle) {
        actualizarReserva(detalle);
        setSaga(detalle);
        setErrorReservas("");
      }
    } catch (e) {
      setErrorReservas(e.message);
    } finally {
      setOcupada(null);
    }
  }

  async function cancelar(sagaId) {
    setOcupada(sagaId);
    try {
      // La cancelación es otra SAGA de compensación en Órdenes: libera auto, hotel y vuelo en orden inverso
      const { cancelarReserva } = await gql(CANCELAR_RESERVA, { sagaId });
      actualizarReserva(cancelarReserva);
      setSaga(cancelarReserva);
      setErrorReservas("");
    } catch (e) {
      setErrorReservas(e.message);
    } finally {
      setOcupada(null);
    }
  }

  async function salir() {
    try {
      await gql(CERRAR_SESION);
    } finally {
      setAvisoAcceso("");
      setReservas(null);
      setSaga(null);
      setUsuario(null);
    }
  }

  function alIniciarSesion(u) {
    setAvisoAcceso("");
    setUsuario(u);
  }

  // Si la sesión expiró a mitad de una reserva, la reserva se retoma apenas vuelve a entrar.
  // (Se hace en un efecto porque reservar() necesita leer el "usuario" ya actualizado.)
  // Al entrar (o cambiar de cuenta) se cargan sus reservas
  useEffect(() => {
    if (usuario) cargarReservas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usuario?.id]);

  useEffect(() => {
    if (usuario && pendiente) {
      const p = pendiente;
      setPendiente(null);
      reservar(p);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usuario]);

  // Comprobando la sesión: pantalla neutra para no mostrar el acceso a quien ya tiene sesión
  if (usuario === undefined) {
    return <div className="topo min-h-screen bg-noche" aria-busy="true" />;
  }
  // Sin sesión: lo único visible es la pantalla de acceso
  if (usuario === null) {
    return <PantallaAcceso onSesion={alIniciarSesion} aviso={avisoAcceso} />;
  }

  return (
    <div className="min-h-screen">
      <Encabezado usuario={usuario} onSalir={salir} />
      <Buscador
        catalogo={catalogo}
        destino={destino}
        noches={noches}
        personas={personas}
        onDestino={setDestino}
        onNoches={setNoches}
        onPersonas={setPersonas}
        onBuscar={() => {
          buscar();
          // En celular los resultados quedan debajo de las ofertas: se llevan a la vista
          if (window.matchMedia("(max-width: 1023px)").matches) {
            refResultados.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }}
        cargando={cargando}
      />
      <Ofertas ofertas={ofertas} conPaquetes={conPaquetes} onVerPaquetes={verPaquetesDe} />

      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section ref={refResultados} aria-labelledby="titulo-resultados" className="min-w-0 scroll-mt-4">
          {buscado?.tipo === "ofertas" ? (
            <ResultadosOfertas
              destino={catalogo.porClave.get(buscado.destino)}
              ofertas={(ofertas ?? []).filter((o) => claveDestino(o) === buscado.destino)}
            />
          ) : (
            <>
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
                    const clave = claveDe(p);
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
            </>
          )}
        </section>

        <aside ref={refReserva} className="scroll-mt-4 space-y-4 lg:sticky lg:top-4 lg:self-start">
          <ResultadoReserva saga={saga} />
          <MisReservas
            reservas={reservas}
            error={errorReservas}
            onActualizar={consultar}
            onCancelar={cancelar}
            ocupada={ocupada}
          />
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
    </div>
  );
}
