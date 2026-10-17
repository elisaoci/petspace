import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // В Docker bind-mount события файловой системы приходят не всегда,
    // поэтому с VITE_USE_POLLING=true dev-сервер опрашивает изменения сам.
    watch: { usePolling: process.env.VITE_USE_POLLING === "true" },
  },
});
