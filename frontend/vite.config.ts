import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "SIRIUS_");
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: env.SIRIUS_API_URL || "http://127.0.0.1:8000",
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
        "/menu": { target: "http://127.0.0.1:3001" },
        "/_next": { target: "http://127.0.0.1:3001" },
      },
    },
  };
});
