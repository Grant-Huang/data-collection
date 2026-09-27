import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Must actually be 8804 -- main.py's CORS allowlist and the tunnel below both assume
    // the dev server is on :8804, not Vite's default :5173. `strictPort` turns a port
    // conflict into a startup error instead of Vite silently picking another port (which
    // would leave the tunnel pointed at a dead port with no obvious symptom).
    port: 8804,
    strictPort: true,
    // Allow access from public hostname via Cloudflare Tunnel
    // (workflow-data.inkpath.cc -> vite dev on :8804 -> /api proxied to :8803).
    host: "0.0.0.0",
    // Vite 5+ blocks unknown Host headers by default. Allow the tunnel hostname
    // + loopback for local network testing.
    allowedHosts: [
      "workflow-data.inkpath.cc",
      "localhost",
      "127.0.0.1",
    ],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8803",
        changeOrigin: true,
      },
    },
  },
});
