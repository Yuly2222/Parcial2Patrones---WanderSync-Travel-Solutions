// Cliente GraphQL mínimo. TODA la comunicación con el backend pasa por aquí y va a /graphql,
// que nginx (o Vite en desarrollo) reenvía al API Gateway. El frontend no conoce ningún otro servicio.
//
// No usamos Apollo ni otra librería: con fetch basta, y así el bundle es pequeño
// y cada petición se puede mostrar tal cual en el "Inspector GraphQL" de la interfaz.

const oyentes = new Set();

/** Suscribe una función que recibe el registro de cada operación (para el inspector). */
export function alOperar(fn) {
  oyentes.add(fn);
  return () => oyentes.delete(fn);
}

export class ErrorGraphQL extends Error {
  constructor(mensaje, status) {
    super(mensaje);
    this.status = status;
  }
}

/**
 * Ejecuta una operación GraphQL.
 * credentials: "same-origin" -> el navegador envía la cookie de sesión (HttpOnly, SameSite=Strict).
 * JavaScript nunca lee ni guarda el token: no hay nada que un XSS pueda robar de localStorage.
 */
export async function gql(query, variables = {}) {
  const nombre = query.match(/(?:query|mutation)\s+(\w+)/)?.[1] ?? "anónima";
  const inicio = performance.now();
  let status = 0;
  let texto = "";
  try {
    const r = await fetch("/graphql", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, variables }),
    });
    status = r.status;
    texto = await r.text();
  } catch {
    throw new ErrorGraphQL("No se pudo contactar al Gateway. ¿Está corriendo docker compose?", 0);
  } finally {
    const registro = {
      id: crypto.randomUUID(),
      nombre,
      query: query.trim(),
      variables,
      status,
      bytes: new Blob([texto]).size,
      ms: Math.round(performance.now() - inicio),
      hora: new Date(),
    };
    oyentes.forEach((fn) => fn(registro));
  }

  let json;
  try {
    json = JSON.parse(texto);
  } catch {
    throw new ErrorGraphQL(`Respuesta inválida del Gateway (HTTP ${status})`, status);
  }
  // GraphQL responde 200 aunque haya errores: vienen en el campo "errors".
  // El rate limiting devuelve 429 con el mensaje del Gateway.
  if (json.errors?.length) {
    throw new ErrorGraphQL(json.errors[0].message, status);
  }
  return json.data;
}
