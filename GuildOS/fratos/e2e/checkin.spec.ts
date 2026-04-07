import { test, expect } from "./fixtures/auth";

test.describe("Check-In", () => {
  test("officer can generate a check-in link", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("text=Chapter Meeting").click();
    await page.locator("button", { hasText: "Open Check-In" }).click();

    await expect(page.locator("text=Check-In Link Active")).toBeVisible();
    await expect(page.locator("text=Expires in:")).toBeVisible();
  });

  test("officer can close a check-in link", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("text=Chapter Meeting").click();
    await page.locator("button", { hasText: "Open Check-In" }).click();
    await expect(page.locator("text=Check-In Link Active")).toBeVisible();

    await page.locator("button", { hasText: "Close Check-In" }).click();
    await expect(page.locator("text=Check-In Link Active")).not.toBeVisible();
  });

  test("member sees check-in button on upcoming event", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("text=Chapter Meeting").click();
    await expect(page.locator("button", { hasText: "Check In" })).toBeVisible();
  });

  test("member can open check-in form and enter code", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("text=Chapter Meeting").click();
    await page.locator("button", { hasText: "Check In" }).click();

    await expect(page.locator("h3", { hasText: "Check In" })).toBeVisible();
    await expect(page.locator("text=Enter the code shown by your officer")).toBeVisible();

    await page.locator("input[placeholder='e.g. A7X9KP']").fill("INVALID");
    await page.locator("button", { hasText: "Check In" }).last().click();
    await expect(page.locator("text=Link expired or invalid")).toBeVisible();
  });
});
