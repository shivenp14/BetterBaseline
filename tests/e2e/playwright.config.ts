import { defineConfig, devices } from "@playwright/test";
import path from "path";

/**
 * Playwright configuration for the isolated Better Baseline E2E suite.
 *
 * Runs a real local backend (FastAPI/uvicorn) and real local frontend (Next.js)
 * before each test run. External network access is blocked inside tests via
 * route interception — the app must work entirely from the local servers.
 *
 * See: https://playwright.dev/docs/test-configuration
 */

const BACKEND_PORT = Number(process.env.BACKEND_PORT || 8001);
const FRONTEND_PORT = Number(process.env.FRONTEND_PORT || 3001);
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const FRONTEND_URL = `http://localhost:${FRONTEND_PORT}`;

// Paths relative to this config file (tests/e2e/)
const REPO_ROOT = path.resolve(__dirname, "../..");
const BACKEND_DIR = path.join(REPO_ROOT, "backend");
const FRONTEND_DIR = path.join(REPO_ROOT, "frontend");
const VENV_PYTHON = process.platform === "win32"
  ? path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe")
  : path.join(BACKEND_DIR, ".venv", "bin", "python");

export default defineConfig({
  testDir: "./tests",
  timeout: 120_000, // 2 min per test — backend startup can be slow on first run
  expect: { timeout: 15_000 },
  fullyParallel: false, // Single worker: share one backend+frontend across all tests
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],

  use: {
    baseURL: FRONTEND_URL,
    // Block all external internet traffic — the suite must pass with no outbound access
    // Individual tests also call page.route() for belt-and-suspenders assertion.
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  webServer: [
    {
      // Real FastAPI backend — uses the shared .venv from the backend dir
      command: [
        VENV_PYTHON,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        String(BACKEND_PORT),
      ].join(" "),
      url: `${BACKEND_URL}/healthz`,
      cwd: BACKEND_DIR,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        ALLOWED_ORIGINS: `["${FRONTEND_URL}"]`,
      },
    },
    {
      // Real Next.js frontend in production mode (pre-built)
      command: `npm run start -- --port ${FRONTEND_PORT}`,
      url: FRONTEND_URL,
      cwd: FRONTEND_DIR,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        NEXT_PUBLIC_API_BASE_URL: BACKEND_URL,
        PORT: String(FRONTEND_PORT),
      },
    },
  ],
});
