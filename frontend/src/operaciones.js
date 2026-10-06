// Operaciones GraphQL que usa la interfaz.
// Cada consulta pide SOLO los campos que la pantalla muestra (sin over-fetching):
// por ejemplo, la tarjeta de paquete no necesita "ciudad" del hotel ni del auto, así que no se pide.

export const PAQUETES = /* GraphQL */ `
  query Paquetes($destino: String!, $noches: Int!, $personas: Int!) {
    paquetes(destino: $destino, noches: $noches, personas: $personas) {
      precioTotal
      habitaciones
      autos
      vuelo { id origen destino precio }
      hotel { id nombre precioNoche rating fuente }
      auto { id modelo precioDia }
    }
  }
`;

export const YO = /* GraphQL */ `
  query Yo {
    yo { id email }
  }
`;

export const REGISTRAR = /* GraphQL */ `
  mutation Registrar($email: String!, $password: String!) {
    registrar(email: $email, password: $password) { id email }
  }
`;

export const INICIAR_SESION = /* GraphQL */ `
  mutation IniciarSesion($email: String!, $password: String!) {
    iniciarSesion(email: $email, password: $password) { id email }
  }
`;

export const CERRAR_SESION = /* GraphQL */ `
  mutation CerrarSesion {
    cerrarSesion
  }
`;

export const RESERVAR = /* GraphQL */ `
  mutation ReservarPaquete($vueloId: Int!, $hotelId: Int!, $autoId: Int!, $personas: Int!) {
    reservarPaquete(vueloId: $vueloId, hotelId: $hotelId, autoId: $autoId, personas: $personas) { sagaId estado }
  }
`;

export const ORDEN = /* GraphQL */ `
  query Orden($sagaId: String!) {
    orden(sagaId: $sagaId) { sagaId estado paso personas }
  }
`;
