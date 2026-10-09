// Operaciones GraphQL que usa la interfaz.
// Cada consulta pide SOLO los campos que la pantalla muestra (sin over-fetching):
// por ejemplo, la tarjeta de paquete no necesita "ciudad" del hotel ni del auto, así que no se pide.

export const PAQUETES = /* GraphQL */ `
  query Paquetes($destino: String!, $noches: Int!, $personas: Int!) {
    paquetes(destino: $destino, noches: $noches, personas: $personas) {
      precioTotal
      habitaciones
      autos
      vuelo { id origen destino precio fuente }
      hotel { id nombre precioNoche rating fuente }
      auto { id modelo precioDia fuente }
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

// Ciudades que hoy tienen paquetes (vuelo + alojamiento cargados)
export const DESTINOS_DISPONIBLES = /* GraphQL */ `
  query Destinos {
    destinos { codigo nombre pais vueloDesde }
  }
`;

// autoId es opcional: en destinos sin alquiler de autos el paquete es vuelo + hotel.
// No se manda ningún precio: el Gateway lo calcula con los datos de cada servicio.
export const RESERVAR = /* GraphQL */ `
  mutation ReservarPaquete($vueloId: Int!, $hotelId: Int!, $autoId: Int, $personas: Int!, $noches: Int!) {
    reservarPaquete(vueloId: $vueloId, hotelId: $hotelId, autoId: $autoId, personas: $personas, noches: $noches) {
      sagaId
      estado
    }
  }
`;

// Campos de una reserva que muestran "Tu reserva" y "Mis reservas"
const CAMPOS_RESERVA = "sagaId estado paso personas noches destino vuelo hotel auto total creado";

export const ORDEN = /* GraphQL */ `
  query Orden($sagaId: String!) {
    orden(sagaId: $sagaId) { ${CAMPOS_RESERVA} }
  }
`;

export const MIS_RESERVAS = /* GraphQL */ `
  query MisReservas {
    misReservas { ${CAMPOS_RESERVA} }
  }
`;

export const CANCELAR_RESERVA = /* GraphQL */ `
  mutation CancelarReserva($sagaId: String!) {
    cancelarReserva(sagaId: $sagaId) { ${CAMPOS_RESERVA} }
  }
`;

// Ofertas de Booking por categoría. Se piden solo los campos que muestran las tarjetas.
export const OFERTAS = /* GraphQL */ `
  query Ofertas {
    ofertas { categoria destino titulo detalle ciudad cantidad precioDesde unidad campana url }
  }
`;
