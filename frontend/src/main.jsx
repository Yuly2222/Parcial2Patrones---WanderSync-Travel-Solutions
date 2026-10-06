import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Fuentes empaquetadas con la app (no se cargan de un CDN externo: la CSP de nginx solo permite 'self')
import "@fontsource-variable/fraunces";
import "@fontsource-variable/fraunces/wght-italic.css";
import "@fontsource-variable/instrument-sans";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
