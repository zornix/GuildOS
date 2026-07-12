import { test as base, type Page } from "@playwright/test";

// Mirrors OFFICER_DEMO_PASSWORD in scripts/seed.py — keep the two in sync.
const OFFICER_DEMO_PASSWORD = "demo-officer-pw";

/**
 * Login through the real login form.
 * Members log in email-only. Officers hit the PASSWORD_REQUIRED reveal
 * (login-form.tsx): after the first submit a password field appears, we fill
 * it and submit again. Requires the dev-auth bypass to be off (pinned via
 * playwright.config.ts webServer.env).
 */
async function loginAs(page: Page, email: string, password?: string) {
  await page.goto("/");
  await page.fill('input[type="email"]', email);
  await page.click('button:has-text("Sign In")');
  if (password) {
    await page.waitForSelector('input[type="password"]');
    await page.fill('input[type="password"]', password);
    await page.click('button:has-text("Sign In")');
  }
  await page.waitForSelector("text=Dashboard");
}

export async function loginAsOfficer(page: Page) {
  await loginAs(page, "jake@tke.org", OFFICER_DEMO_PASSWORD);
}

export async function loginAsMember(page: Page) {
  await loginAs(page, "ryan@tke.org");
}

// Log in as a specific seeded member (all are email-only). Used by the excuse
// specs so each mutating test targets a distinct (member, event) pair —
// excuse uniqueness is per member+event, so distinct members never collide.
export async function loginAsMemberEmail(page: Page, email: string) {
  await loginAs(page, email);
}

interface Fixtures {
  officerPage: Page;
  memberPage: Page;
}

export const test = base.extend<Fixtures>({
  officerPage: async ({ page }, runFixture) => {
    await loginAsOfficer(page);
    await runFixture(page);
  },
  memberPage: async ({ page }, runFixture) => {
    await loginAsMember(page);
    await runFixture(page);
  },
});

export { expect } from "@playwright/test";
