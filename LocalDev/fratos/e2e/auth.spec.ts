import { test, expect } from "@playwright/test";

// Officers have a seeded bcrypt password (scripts/seed.py OFFICER_DEMO_PASSWORD).
const OFFICER_DEMO_PASSWORD = "demo-officer-pw";

test.describe("Authentication", () => {
  test("shows login page on initial visit", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("text=FraternityOS")).toBeVisible();
    await expect(page.getByText("Sign in", { exact: true })).toBeVisible();
  });

  test("member logs in with email only", async ({ page }) => {
    await page.goto("/");
    await page.locator("input[type='email']").fill("ryan@tke.org");
    await page.locator("button", { hasText: "Sign In" }).click();
    await expect(page.locator("h1", { hasText: "Dashboard" })).toBeVisible();
  });

  test("officer login requires a password, then reaches dashboard", async ({ page }) => {
    await page.goto("/");
    await page.locator("input[type='email']").fill("jake@tke.org");
    await page.locator("button", { hasText: "Sign In" }).click();

    // PASSWORD_REQUIRED reveal
    await expect(page.locator("text=Officers must enter a password")).toBeVisible();
    await page.locator("input[type='password']").fill(OFFICER_DEMO_PASSWORD);
    await page.locator("button", { hasText: "Sign In" }).click();

    await expect(page.locator("h1", { hasText: "Dashboard" })).toBeVisible();
  });

  test("login with invalid email shows error", async ({ page }) => {
    await page.goto("/");
    await page.locator("input[type='email']").fill("unknown@test.org");
    await page.locator("button", { hasText: "Sign In" }).click();
    await expect(page.locator("text=No active member found with that email")).toBeVisible();
  });

  test("logout returns to login screen", async ({ page }) => {
    await page.goto("/");
    await page.locator("input[type='email']").fill("ryan@tke.org");
    await page.locator("button", { hasText: "Sign In" }).click();
    await expect(page.locator("h1", { hasText: "Dashboard" })).toBeVisible();
    await page.locator("button[title='Sign out']").click();
    await expect(page.getByText("Sign in", { exact: true })).toBeVisible();
  });
});
