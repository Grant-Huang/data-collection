import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
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
