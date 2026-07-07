import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// 127.0.0.1, not localhost: uvicorn binds IPv4 loopback only, and a "localhost"
// target can resolve to ::1 and hit whatever else squats the port on IPv6.
const backendTarget = `http://127.0.0.1:${Number(process.env.BACKEND_PORT) || 8000}`;

export default defineConfig({
  plugins: [react()],
  server: {
    // strictPort: a silent hop to 5174 would break the backend's FRONTEND_URL
    // (CORS + post-callback redirect) — fail loudly instead.
    port: Number(process.env.FRONTEND_PORT) || 5173,
    strictPort: true,
    proxy: {
      "/api": backendTarget,
      "/launch": backendTarget,
      "/callback": backendTarget,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
    exclude: ["**/node_modules/**", "**/e2e/**"],
  },
});
