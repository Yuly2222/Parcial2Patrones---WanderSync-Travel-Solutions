// Registro e inicio de sesión. La sesión vive en una cookie HttpOnly que pone el Gateway:
// este componente nunca ve ni guarda el token.
import { useEffect, useRef, useState } from "react";
import { gql } from "../api";
import { INICIAR_SESION, REGISTRAR } from "../operaciones";

export default function DialogoAcceso({ abierto, modoInicial = "entrar", motivo, onCerrar, onSesion }) {
  const ref = useRef(null);
  const [modo, setModo] = useState(modoInicial);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (abierto && !d.open) {
      // Cada vez que se abre: arranca en el modo pedido ("Crear cuenta" o "Iniciar sesión") y sin errores viejos
      setModo(modoInicial);
      setError("");
      d.showModal();
    }
    if (!abierto && d.open) d.close();
  }, [abierto, modoInicial]);

  async function enviar(e) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      if (modo === "registro") {
        await gql(REGISTRAR, { email, password });
      }
      // Al registrarse se inicia sesión de inmediato. El Gateway emite un ID de sesión NUEVO
      // en cada login (mitigación de Session Fixation).
      const { iniciarSesion } = await gql(INICIAR_SESION, { email, password });
      setPassword("");
      onSesion(iniciarSesion);
    } catch (err) {
      setError(err.message);
    } finally {
      setEnviando(false);
    }
  }

  const registro = modo === "registro";

  return (
    <dialog
      ref={ref}
      onClose={onCerrar}
      onClick={(e) => e.target === ref.current && onCerrar()}
      className="m-auto w-[min(26rem,calc(100%-2rem))] rounded-2xl bg-papel p-0 text-tinta shadow-2xl backdrop:bg-noche/70"
    >
      <form onSubmit={enviar} className="p-6">
        <div className="flex items-start justify-between">
          <h2 className="font-display text-2xl font-semibold tracking-tight">
            {registro ? "Crear cuenta" : "Iniciar sesión"}
          </h2>
          <button type="button" onClick={onCerrar} aria-label="Cerrar" className="text-xl text-piedra hover:text-tinta">
            ×
          </button>
        </div>
        <p className="mt-1 text-sm text-acero">
          {motivo ??
            (registro
              ? "Crea tu cuenta para reservar y consultar tus viajes."
              : "Entra con tu cuenta para reservar y consultar tus viajes.")}
        </p>

        <label className="mt-5 block text-sm font-medium" htmlFor="email">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          maxLength={254}
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-lg border border-niebla bg-white px-3 py-2.5"
        />

        <label className="mt-4 block text-sm font-medium" htmlFor="password">
          Contraseña
        </label>
        <input
          id="password"
          type="password"
          required
          minLength={registro ? 10 : undefined}
          maxLength={128}
          autoComplete={registro ? "new-password" : "current-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-lg border border-niebla bg-white px-3 py-2.5"
        />
        {registro && <p className="mt-1 text-xs text-piedra">Mínimo 10 caracteres.</p>}

        {error && (
          <p role="alert" className="mt-4 rounded-lg bg-[#b4553f]/10 px-3 py-2 text-sm text-[#9b4533]">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={enviando}
          className="mt-5 w-full rounded-xl bg-selva py-3 font-semibold text-papel transition hover:bg-salvia disabled:opacity-60"
        >
          {enviando ? "Un momento…" : registro ? "Crear cuenta" : "Entrar"}
        </button>

        <p className="mt-4 text-center text-sm text-acero">
          {registro ? "¿Ya tienes cuenta?" : "¿No tienes cuenta?"}{" "}
          <button
            type="button"
            onClick={() => {
              setModo(registro ? "entrar" : "registro");
              setError("");
            }}
            className="font-semibold text-selva underline-offset-2 hover:underline"
          >
            {registro ? "Inicia sesión" : "Crea una cuenta"}
          </button>
        </p>
      </form>
    </dialog>
  );
}
