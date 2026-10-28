/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to the FastAPI backend, so the browser talks to
// one origin and the backend's CORS list only matters for other setups.
const backend = process.env.PIXELCACHE_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // Recharts is most of the bundle; keep it in its own cacheable chunk.
    rollupOptions: { output: { manualChunks: { recharts: ["recharts"] } } },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
