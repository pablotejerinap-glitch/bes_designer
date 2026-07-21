import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// El front llama a rutas /api/* y Vite las proxya al backend FastAPI en dev,
// evitando CORS. En producción se sirve tras el mismo origen o se configura
// VITE_API_BASE.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
