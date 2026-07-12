import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
    // The e2e specs exercise the real login form, so the dev-auth auto-login
    // bypass (which never renders the form) must be off. A real env var beats
    // fratos/.env.local's NEXT_PUBLIC_DEV_AUTH_BYPASS=1 in Next.
    env: { NEXT_PUBLIC_DEV_AUTH_BYPASS: "0" },
  },
});
