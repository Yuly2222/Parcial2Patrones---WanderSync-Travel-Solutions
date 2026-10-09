// Catálogo de TODOS los destinos de la página, para el selector "Selecciona tu destino":
//   - los que tienen paquetes WanderSync (query destinos: hay vuelo y alojamiento), y
//   - los que solo aparecen en las ofertas de Booking (vuelos, alojamiento, coches, atracciones).
// La clave de un destino es su código IATA cuando se conoce ("CUN") y si no, su nombre normalizado
// ("n:aeropuerto de faro"); así "Cartagena" (coches) y "Cartagena de Indias" (vuelos) son el mismo destino (CTG).
import { normalizar } from "./formato";

export const claveDe = (oferta) => oferta.ciudad ?? `n:${normalizar(oferta.destino)}`;

// Qué nombre usar cuando varias ofertas nombran el mismo destino (el de vuelos es el más "de ciudad")
const PRIORIDAD = { vuelos: 0, alojamiento: 1, atracciones: 2, coches: 3 };

export function construirCatalogo(destinos, ofertas) {
  const mapa = new Map();
  for (const d of destinos ?? []) {
    mapa.set(d.codigo, {
      clave: d.codigo,
      codigo: d.codigo,
      nombre: d.nombre,
      pais: d.pais,
      paquetes: true,
      vueloDesde: d.vueloDesde,
      categorias: new Set(),
      prioridad: -1,
    });
  }
  for (const o of ofertas ?? []) {
    const clave = claveDe(o);
    const nombre = o.destino;
    let d = mapa.get(clave);
    if (!d) {
      d = {
        clave,
        codigo: o.ciudad,
        nombre,
        pais: null,
        paquetes: false,
        categorias: new Set(),
        prioridad: 9,
      };
      mapa.set(clave, d);
    }
    d.categorias.add(o.categoria);
    if (PRIORIDAD[o.categoria] < d.prioridad) {
      d.nombre = nombre;
      d.prioridad = PRIORIDAD[o.categoria];
    }
    if (o.categoria === "vuelos" && o.detalle) d.pais ??= o.detalle; // en vuelos, "detalle" es el país
  }
  const orden = (a, b) => a.nombre.localeCompare(b.nombre, "es");
  const todos = [...mapa.values()];
  return {
    porClave: mapa,
    conPaquetes: todos.filter((d) => d.paquetes).sort(orden),
    soloOfertas: todos.filter((d) => !d.paquetes).sort(orden),
  };
}
