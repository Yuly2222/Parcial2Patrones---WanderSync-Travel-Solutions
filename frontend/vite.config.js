import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// En desarrollo (npm run dev) Vite reenvía /graphql al Gateway que corre en Docker.
// Así el navegador ve un solo origen (localhost:5173) y la cookie SameSite=Strict funciona,
// igual que en producción, donde nginx hace el mismo trabajo (ver nginx.conf).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Permite abrir el servidor de desarrollo por la URL pública del túnel (plan B, ver README)
    allowedHosts: [".trycloudflare.com"],
    proxy: {
      "/graphql": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
