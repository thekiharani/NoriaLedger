import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev server proxies /api to the local edge (Caddy), which pins requests to the
// hub site exactly like production. Start the stack first: noria.sh up
const edge = process.env.NORIA_EDGE_URL ?? "http://localhost:8080";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: { "/api": { target: edge, changeOrigin: true } },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 800 },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
