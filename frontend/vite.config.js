import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, calls to /api are forwarded to the FastAPI backend (no CORS issues).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_API_PROXY || "http://localhost:8000", changeOrigin: true } },
  },
});
