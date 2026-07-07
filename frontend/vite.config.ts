import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // strictPort: a silent hop to 5174 would break the backend's FRONTEND_URL
    // (CORS + post-callback redirect) — fail loudly instead.
    port: Number(process.env.FRONTEND_PORT) || 5173,
    strictPort: true,
    proxy: {
      "/api": "http://localhost:8000",
      "/launch": "http://localhost:8000",
      "/callback": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
    exclude: ["**/node_modules/**", "**/e2e/**"],
  },
});
