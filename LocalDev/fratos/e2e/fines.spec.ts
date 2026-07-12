import { test, expect } from "./fixtures/auth";

test.describe("Fines", () => {
  test("officer can view all fines", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Fines" }).click();
    await expect(page.locator("h1", { hasText: "Fines" })).toBeVisible();
    // Seed creates unpaid fines "Missed Philanthropy Event (unexcused)" (x3).
    await expect(page.locator("text=Missed Philanthropy Event").first()).toBeVisible();
  });

  test("officer can filter fines by status", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Fines" }).click();

    // Philanthropy fines are all unpaid in the seed.
    await page.locator("button", { hasText: /^unpaid/ }).click();
    await expect(page.locator("text=Missed Philanthropy Event").first()).toBeVisible();

    await page.locator("button", { hasText: /^paid/ }).click();
    await expect(page.locator("text=Missed Philanthropy Event")).not.toBeVisible();
  });

  test("officer can waive a fine", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Fines" }).click();
    await page.locator("button", { hasText: "Waive" }).first().click();
    await expect(page.locator("text=Waived")).toBeVisible();
  });

  test("member can view their own fines on dashboard", async ({ memberPage: page }) => {
    await expect(page.locator("text=My Unpaid Fines")).toBeVisible();
  });
});
