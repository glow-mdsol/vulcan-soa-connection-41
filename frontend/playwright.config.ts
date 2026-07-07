import { defineConfig } from "@playwright/test";

const frontendPort = Number(process.env.FRONTEND_PORT) || 5173;

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: `http://localhost:${frontendPort}`,
  },
});
