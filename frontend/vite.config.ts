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
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        // Long-lived vendor chunks: app releases do not invalidate cached libraries.
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return "react";
          if (id.includes("@tanstack")) return "tanstack";
          if (/@radix-ui|lucide-react|sonner|@floating-ui/.test(id)) return "ui";
          if (id.includes("/zod/")) return "zod";
          return "vendor";
        },
      },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
