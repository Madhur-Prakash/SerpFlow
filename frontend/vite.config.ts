import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    host: true,
    fs: {
      // The docs browser reads ../docs/**/*.md directly, so the published site
      // and the repository can never describe different systems.
      allow: [path.resolve(__dirname, ".."), path.resolve(__dirname)],
    },
    proxy: {
      // The SSE stream and every API call go through the same origin in dev,
      // so EventSource needs no CORS dance and cookies behave as in production.
      "/v1": {
        target: process.env.VITE_API_BASE_URL || "http://localhost:8000",
        changeOrigin: true,
      },
      "/healthz": { target: process.env.VITE_API_BASE_URL || "http://localhost:8000" },
      "/readyz": { target: process.env.VITE_API_BASE_URL || "http://localhost:8000" },
      "/metrics": { target: process.env.VITE_API_BASE_URL || "http://localhost:8000" },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          motion: ["framer-motion", "lenis"],
          // GSAP and its plugins are only used by the marketing pages, which
          // import them dynamically. Keeping them out of a shared chunk is
          // what stops the console downloading ScrollTrigger it never runs.
        },
      },
    },
  },
});
