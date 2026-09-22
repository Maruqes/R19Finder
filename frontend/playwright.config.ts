import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:8001",
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "../.venv/bin/python ../api/tests/serve_frontend.py",
    url: "http://127.0.0.1:8001/health",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
