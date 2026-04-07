import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test("shows login page on initial visit", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("text=FraternityOS")).toBeVisible();
    await expect(page.getByText("Officer sign-in")).toBeVisible();
  });

  test("login with valid email navigates to dashboard", async ({ page }) => {
    await page.goto("/");
    await page.locator("input[type='email']").fill("jake@tke.org");
    await page.locator("button", { hasText: "Sign In" }).click();
    await expect(page.locator("h1", { hasText: "Dashboard" })).toBeVisible();
    await expect(page.locator("text=officer").first()).toBeVisible();
  });

  test("login with invalid email shows error", async ({ page }) => {
    await page.goto("/");
    await page.locator("input[type='email']").fill("unknown@test.org");
    await page.locator("button", { hasText: "Sign In" }).click();
    await expect(page.getByText("No active member found with that email")).toBeVisible();
  });

  test("logout returns to login screen", async ({ page }) => {
    await page.goto("/");
    await page.locator("input[type='email']").fill("jake@tke.org");
    await page.locator("button", { hasText: "Sign In" }).click();
    await expect(page.locator("h1", { hasText: "Dashboard" })).toBeVisible();
    await page.locator("button[title='Sign out']").click();
    await expect(page.getByText("Officer sign-in")).toBeVisible();
  });
});
