import { defineConfig } from "@playwright/test";

// Runs against the real stack through the public edge (noria.sh up + seed).
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.NORIA_BASE_URL ?? "http://localhost:8080",
    screenshot: "only-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {},
  },
});
