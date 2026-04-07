import { test as base, type Page } from "@playwright/test";

/**
 * Login by entering an email on the login screen.
 * Works with the dev-login endpoint (DATABASE_URL set).
 */
async function loginAs(page: Page, email: string) {
  await page.goto("/");
  await page.fill('input[type="email"]', email);
  await page.click('button:has-text("Sign In")');
  await page.waitForSelector("text=Dashboard");
}

export async function loginAsOfficer(page: Page) {
  await loginAs(page, "jake@tke.org");
}

export async function loginAsMember(page: Page) {
  await loginAs(page, "ryan@tke.org");
}

export async function loginAsAlex(page: Page) {
  await loginAs(page, "alex@tke.org");
}

export async function loginAsTyler(page: Page) {
  await loginAs(page, "tyler@tke.org");
}

interface Fixtures {
  officerPage: Page;
  memberPage: Page;
  /** Second member (Alex) — avoids excuse-submit conflicts when tests share one event. */
  memberAltPage: Page;
  /** Third member (Tyler) — clean duplicate-excuse scenarios vs. Ryan/Alex DB state. */
  memberTylerPage: Page;
}

export const test = base.extend<Fixtures>({
  officerPage: async ({ page }, use) => {
    await loginAsOfficer(page);
    await use(page);
  },
  memberPage: async ({ page }, use) => {
    await loginAsMember(page);
    await use(page);
  },
  memberAltPage: async ({ page }, use) => {
    await loginAsAlex(page);
    await use(page);
  },
  memberTylerPage: async ({ page }, use) => {
    await loginAsTyler(page);
    await use(page);
  },
});

export { expect } from "@playwright/test";
