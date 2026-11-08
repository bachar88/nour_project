import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// `npm run build:preview` (mode "preview") makes ONE self-contained HTML file (dist-preview/index.html)
// that runs without the backend: src/api.js is swapped for src/preview/localApi.js.
const swapApiForPreview = {
  name: "nour-preview-api",
  enforce: "pre",
  async resolveId(source, importer) {
    if (!importer || !source.endsWith("api.js") || importer.includes("/preview/")) return null;
    const resolved = path.resolve(path.dirname(importer), source);
    if (resolved === path.resolve(__dirname, "src/api.js")) return path.resolve(__dirname, "src/preview/localApi.js");
    return null;
  },
};

export default defineConfig(({ mode }) => {
  const preview = mode === "preview";
  return {
    plugins: [react(), ...(preview ? [swapApiForPreview, viteSingleFile()] : [])],
    build: preview ? { outDir: "dist-preview", assetsInlineLimit: 100_000_000 } : {},
    server: {
      port: 5173,
      // In dev, calls to /api are forwarded to the FastAPI backend (no CORS issues).
      proxy: { "/api": { target: process.env.VITE_API_PROXY || "http://localhost:8000", changeOrigin: true } },
    },
  };
});
