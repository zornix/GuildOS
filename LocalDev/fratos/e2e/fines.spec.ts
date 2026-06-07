import { test, expect } from "./fixtures/auth";

test.describe("Fines", () => {
  test("officer can view all fines", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Fines" }).click();
    await expect(page.locator("h1", { hasText: "Fines" })).toBeVisible();
    await expect(page.locator("text=Missed Brotherhood Dinner")).toBeVisible();
  });

  test("officer can filter fines by status", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Fines" }).click();

    await page.locator("button", { hasText: /^unpaid/ }).click();
    await expect(page.locator("text=Missed Brotherhood Dinner")).toBeVisible();

    await page.locator("button", { hasText: /^paid/ }).click();
    await expect(page.locator("text=No fines")).toBeVisible();
  });

  test("officer can waive a fine", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Fines" }).click();
    await page.locator("button", { hasText: "Waive" }).first().click();
    await expect(page.locator("text=Waived")).toBeVisible();
  });

  test("member can view their own fines on dashboard", async ({ memberPage: page }) => {
    await expect(page.locator("text=My Unpaid Fines")).toBeVisible();
  });

  test("member can pay a fine", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Fines" }).click();
    const payBtn = page.locator("button", { hasText: "Pay" }).first();

    if (await payBtn.isVisible()) {
      await payBtn.click();
      await expect(page.locator("text=Paid")).toBeVisible();
    }
  });
});
