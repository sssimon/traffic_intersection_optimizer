import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Lee el puerto que escribió backend/run.py en `../.dev-port`.
// Fallback a 8765 si el archivo no existe todavía (primer arranque).
function backendPort(): number {
  try {
    const p = readFileSync(resolve(__dirname, "..", ".dev-port"), "utf-8").trim();
    const n = parseInt(p, 10);
    if (!isNaN(n)) return n;
  } catch {
    // archivo no existe aún — usar default
  }
  return 8765;
}

export default defineConfig(() => {
  const port = backendPort();
  // eslint-disable-next-line no-console
  console.log(`[vite] proxying /api → http://127.0.0.1:${port}`);
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: false,
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${port}`,
          changeOrigin: true,
        },
      },
    },
  };
});
