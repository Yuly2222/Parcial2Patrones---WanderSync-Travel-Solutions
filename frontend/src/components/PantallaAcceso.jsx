// Pantalla de acceso: lo primero que ve quien no tiene sesión. Nada de la app se muestra hasta entrar.
// La sesión vive en una cookie HttpOnly que pone el Gateway: este componente nunca ve ni guarda el token.
import { useId, useState } from "react";
import { gql } from "../api";
import { INICIAR_SESION, REGISTRAR } from "../operaciones";

const MIN = 10;

function Campo({ id, etiqueta, children, ayuda, error }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-tinta">
        {etiqueta}
      </label>
      <div className="mt-1.5">{children}</div>
      {error ? (
        <p id={`${id}-ayuda`} className="mt-1.5 text-xs text-[#9b4533]">
          {error}
        </p>
      ) : (
        ayuda && (
          <p id={`${id}-ayuda`} className="mt-1.5 text-xs text-piedra">
            {ayuda}
          </p>
        )
      )}
    </div>
  );
}

const claseInput =
  "w-full rounded-xl border border-niebla bg-white px-3.5 py-3 text-[15px] text-tinta transition outline-none placeholder:text-piedra/70 focus:border-selva focus:ring-2 focus:ring-musgo/30 focus-visible:outline-none";

export default function PantallaAcceso({ onSesion, aviso }) {
  const id = useId();
  const [modo, setModo] = useState("entrar");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [ver, setVer] = useState(false);
  const [error, setError] = useState("");
  const [intentado, setIntentado] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const registro = modo === "registro";
  const corta = registro && password.length > 0 && password.length < MIN;
  const noCoincide = registro && confirmacion.length > 0 && confirmacion !== password;

  function cambiarModo(m) {
    setModo(m);
    setError("");
    setIntentado(false);
    setConfirmacion("");
  }

  async function enviar(e) {
    e.preventDefault();
    setIntentado(true);
    setError("");
    if (registro && (password.length < MIN || password !== confirmacion)) return;
    setEnviando(true);
    try {
      if (registro) await gql(REGISTRAR, { email, password });
      // Al registrarse se entra de inmediato. El Gateway emite un ID de sesión NUEVO en cada login
      // (mitigación de Session Fixation).
      const { iniciarSesion } = await gql(INICIAR_SESION, { email, password });
      onSesion(iniciarSesion);
    } catch (err) {
      setError(
        registro && /registrar/i.test(err.message)
          ? "Ya existe una cuenta con ese correo. Inicia sesión."
          : err.message === "Credenciales inválidas"
            ? "El correo o la contraseña no son correctos."
            : err.message,
      );
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      {/* Marca */}
      <section className="topo relative flex flex-col justify-between overflow-hidden bg-noche px-6 py-8 text-papel sm:px-10 lg:py-12">
        <div className="flex items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="size-9" />
          <span className="font-display text-2xl font-semibold tracking-tight">WanderSync</span>
        </div>

        <div className="mt-10 max-w-lg lg:mt-0">
          <p className="font-mono text-xs tracking-[0.2em] text-musgo uppercase">Paquetes de viaje · Colombia</p>
          <h1 className="mt-3 font-display text-4xl leading-[1.05] font-semibold tracking-tight sm:text-5xl lg:text-6xl">
            Vuelo, hotel y auto.
            <span className="block text-mostaza italic">Todo o nada.</span>
          </h1>
          <ul className="mt-8 hidden space-y-4 text-niebla sm:block">
            {[
              ["Una sola reserva", "Tu vuelo, tu hotel y tu auto se confirman juntos."],
              ["Nunca a medias", "Si una parte falla, cancelamos el resto automáticamente."],
              ["Precios reales", "Comparamos tarifas de Hostelworld y Trivago por ti."],
            ].map(([t, d]) => (
              <li key={t} className="flex gap-3">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-musgo" aria-hidden="true" />
                <span>
                  <strong className="font-semibold text-papel">{t}.</strong> {d}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="mt-10 hidden text-xs text-pizarra lg:block">Medellín · Cartagena · Santa Marta</p>
      </section>

      {/* Formulario */}
      <main className="flex items-center justify-center bg-papel px-5 py-10 sm:px-10">
        <div className="w-full max-w-[26rem]">
          <h2 className="font-display text-3xl font-semibold tracking-tight">
            {registro ? "Crea tu cuenta" : "Te damos la bienvenida"}
          </h2>
          <p className="mt-1.5 text-acero">
            {registro ? "Es gratis y toma menos de un minuto." : "Entra para buscar y reservar tu próximo viaje."}
          </p>

          {aviso && (
            <p role="status" className="mt-5 rounded-xl bg-mostaza/15 px-4 py-3 text-sm text-oliva-oscuro">
              {aviso}
            </p>
          )}

          <div role="tablist" aria-label="Acceso" className="mt-6 grid grid-cols-2 rounded-xl bg-niebla/50 p-1">
            {[
              ["entrar", "Iniciar sesión"],
              ["registro", "Crear cuenta"],
            ].map(([m, t]) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={modo === m}
                onClick={() => cambiarModo(m)}
                className={`rounded-lg py-2.5 text-sm font-semibold transition ${
                  modo === m ? "bg-white text-tinta shadow-sm" : "text-acero hover:text-tinta"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <form onSubmit={enviar} noValidate className="mt-6 space-y-5">
            <Campo id={`${id}-email`} etiqueta="Correo electrónico">
              <input
                id={`${id}-email`}
                type="email"
                required
                maxLength={254}
                autoComplete="email"
                inputMode="email"
                placeholder="tu@correo.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={claseInput}
              />
            </Campo>

            <Campo
              id={`${id}-password`}
              etiqueta="Contraseña"
              ayuda={registro ? `Mínimo ${MIN} caracteres.` : undefined}
              error={(intentado || password.length >= 3) && corta ? `Te faltan ${MIN - password.length} caracteres.` : ""}
            >
              <div className="relative">
                <input
                  id={`${id}-password`}
                  type={ver ? "text" : "password"}
                  required
                  minLength={registro ? MIN : undefined}
                  maxLength={128}
                  autoComplete={registro ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-describedby={`${id}-password-ayuda`}
                  className={`${claseInput} pr-20`}
                />
                <button
                  type="button"
                  onClick={() => setVer((v) => !v)}
                  aria-pressed={ver}
                  className="absolute inset-y-0 right-0 px-4 text-sm font-medium text-acero hover:text-tinta"
                >
                  {ver ? "Ocultar" : "Mostrar"}
                </button>
              </div>
            </Campo>

            {registro && (
              <Campo
                id={`${id}-confirmacion`}
                etiqueta="Repite la contraseña"
                error={(intentado || confirmacion.length >= password.length) && noCoincide ? "Las contraseñas no coinciden." : ""}
              >
                <input
                  id={`${id}-confirmacion`}
                  type={ver ? "text" : "password"}
                  required
                  maxLength={128}
                  autoComplete="new-password"
                  value={confirmacion}
                  onChange={(e) => setConfirmacion(e.target.value)}
                  className={claseInput}
                />
              </Campo>
            )}

            {error && (
              <p role="alert" className="rounded-xl bg-[#b4553f]/10 px-4 py-3 text-sm text-[#9b4533]">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={enviando || !email || !password}
              className="w-full rounded-xl bg-selva py-3.5 font-semibold text-papel transition hover:bg-salvia disabled:cursor-not-allowed disabled:opacity-50"
            >
              {enviando ? "Un momento…" : registro ? "Crear cuenta" : "Entrar"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-acero">
            {registro ? "¿Ya tienes cuenta? " : "¿Primera vez en WanderSync? "}
            <button
              type="button"
              onClick={() => cambiarModo(registro ? "entrar" : "registro")}
              className="font-semibold text-selva underline-offset-2 hover:underline"
            >
              {registro ? "Inicia sesión" : "Crea una cuenta"}
            </button>
          </p>
        </div>
      </main>
    </div>
  );
}
