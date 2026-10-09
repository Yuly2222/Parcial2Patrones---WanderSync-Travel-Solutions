// Barra superior (solo con sesión): marca, cuenta y, solo en modo demo (?demo), los paneles técnicos.
import { DEMO } from "../formato";

const host = typeof window !== "undefined" ? window.location.hostname : "localhost";

const PANELES = [
  { nombre: "Prefect", url: `http://${host}:4200`, titulo: "Flows, tareas y reintentos" },
  { nombre: "Dask", url: `http://${host}:8787`, titulo: "Workers y tareas distribuidas" },
  { nombre: "GraphiQL", url: "/graphql", titulo: "Explorador del API Gateway" },
];

export default function Encabezado({ usuario, onSalir }) {
  return (
    <header className="bg-noche text-papel">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-3 px-4 py-4 sm:gap-x-6 sm:px-6">
        <a href={DEMO ? "/?demo" : "/"} className="flex items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="size-7 sm:size-8" />
          <span className="font-display text-lg font-semibold tracking-tight sm:text-xl">WanderSync</span>
        </a>

        {DEMO && (
          <nav aria-label="Paneles técnicos (modo demo)" className="flex items-center gap-1 text-sm">
            {PANELES.map((p) => (
              <a
                key={p.nombre}
                href={p.url}
                target="_blank"
                rel="noreferrer"
                title={p.titulo}
                className="rounded-md px-2.5 py-1.5 text-niebla transition hover:bg-acero/60 hover:text-papel"
              >
                {p.nombre} <span aria-hidden="true" className="text-pizarra">↗</span>
              </a>
            ))}
          </nav>
        )}

        <div className="ml-auto flex items-center gap-2 text-sm sm:gap-3">
          <a
            href="#titulo-mis-reservas"
            className="rounded-md px-2 py-1.5 font-medium whitespace-nowrap text-niebla transition hover:bg-acero/60 hover:text-papel sm:px-2.5"
          >
            Mis reservas
          </a>
          <span className="hidden items-center gap-2 text-niebla sm:flex">
            <span className="size-2 rounded-full bg-musgo" aria-hidden="true" />
            {usuario.email}
          </span>
          <button
            onClick={onSalir}
            className="rounded-md border border-acero px-3 py-1.5 font-medium transition hover:border-bruma"
          >
            <span className="sm:hidden">Salir</span>
            <span className="hidden sm:inline">Cerrar sesión</span>
          </button>
        </div>
      </div>
    </header>
  );
}
