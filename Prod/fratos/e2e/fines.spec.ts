import { test, expect } from "./fixtures/auth";
import { FINE_REASON_EVENT_0, MEMBERS } from "./test-data";

test.describe("Fines", () => {
  test.describe.configure({ mode: "serial" });
  test("officer can view all fines", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Fines" }).click();
    await expect(page.locator("h1", { hasText: "Fines" })).toBeVisible();
    await expect(page.getByText(FINE_REASON_EVENT_0, { exact: true }).first()).toBeVisible();
  });

  test("officer can filter fines by status", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Fines" }).click();

    await page.getByRole("button", { name: /unpaid/i }).click();
    await expect(page.getByRole("button", { name: "Waive" }).first()).toBeVisible();
    await expect(page.getByText("(unexcused)", { exact: false }).first()).toBeVisible();

    await page.getByRole("button", { name: /^paid\b/i }).click();
    await expect(page.getByText(MEMBERS.ethan, { exact: true }).first()).toBeVisible();
  });

  test("officer can waive a fine", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Fines" }).click();
    await page.getByRole("button", { name: /unpaid/i }).click();
    await page.locator("button", { hasText: "Waive" }).first().click();
    await expect(page.getByText("waived", { exact: true }).first()).toBeVisible({ timeout: 10000 });
  });

  test("member can view their own fines on dashboard", async ({ memberPage: page }) => {
    await expect(page.locator("text=My Unpaid Fines")).toBeVisible();
  });

  test("member does not see pay fine action", async ({ memberPage: page }) => {
    await expect(page.locator("button", { hasText: "Pay" })).toHaveCount(0);
    await page.locator("button", { hasText: "Fines" }).click();
    await expect(page.locator("button", { hasText: "Pay" })).toHaveCount(0);
  });
});
