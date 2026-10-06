// Inspector GraphQL: muestra cada operación que el frontend envió al Gateway,
// con su consulta exacta, el tamaño de la respuesta y el tiempo.
// Sirve para demostrar en vivo que el cliente pide solo los campos que usa (sin over-fetching)
// y que TODO pasa por un único endpoint: /graphql.
import { useEffect, useState } from "react";
import { alOperar } from "../api";

const kb = (b) => (b < 1024 ? `${b} B` : `${(b / 1024).toFixed(1)} KB`);

export default function Inspector() {
  const [ops, setOps] = useState([]);
  const [abierta, setAbierta] = useState(null);

  useEffect(() => alOperar((r) => setOps((prev) => [r, ...prev].slice(0, 15))), []);

  return (
    <section className="rounded-2xl bg-noche p-5 text-papel">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-lg font-semibold">Inspector GraphQL</h2>
        <span className="font-mono text-[11px] text-bruma">POST /graphql</span>
      </div>
      {ops.length === 0 ? (
        <p className="mt-2 text-sm text-niebla">Aquí aparecerá cada consulta y mutación enviada al Gateway.</p>
      ) : (
        <ul className="mt-3 space-y-1.5">
          {ops.map((o) => (
            <li key={o.id}>
              <button
                onClick={() => setAbierta(abierta === o.id ? null : o.id)}
                aria-expanded={abierta === o.id}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left font-mono text-xs transition hover:bg-acero/50"
              >
                <span
                  className={`w-8 shrink-0 ${o.status >= 400 || o.status === 0 ? "text-[#e08a72]" : "text-musgo"}`}
                >
                  {o.status || "—"}
                </span>
                <span className="flex-1 truncate">{o.nombre}</span>
                <span className="text-bruma">{kb(o.bytes)}</span>
                <span className="w-12 text-right text-pizarra">{o.ms} ms</span>
              </button>
              {abierta === o.id && (
                <pre className="mt-1 overflow-x-auto rounded-lg bg-black/25 p-3 font-mono text-[11px] leading-relaxed text-niebla">
                  {o.query}
                  {Object.keys(o.variables).length > 0 &&
                    `\n\n# variables\n${JSON.stringify(
                      o.variables,
                      (k, v) => (k === "password" ? "••••••" : v),
                      2,
                    )}`}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
