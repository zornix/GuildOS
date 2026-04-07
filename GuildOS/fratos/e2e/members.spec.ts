import { test, expect } from "./fixtures/auth";

test.describe("Members", () => {
  test("officer can view chapter roster", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Members" }).click();
    await expect(page.locator("h1", { hasText: "Members" })).toBeVisible();
    await expect(page.locator("text=Chapter Roster")).toBeVisible();
    await expect(page.locator("text=Alex Johnson")).toBeVisible();
    await expect(page.locator("text=Marcus Lee")).toBeVisible();
  });

  test("officer sees role badges on members", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Members" }).click();
    const officerBadges = page.locator("text=officer");
    expect(await officerBadges.count()).toBeGreaterThanOrEqual(1);
  });

  test("member can view chapter roster", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Members" }).click();
    await expect(page.locator("text=Chapter Roster")).toBeVisible();
    await expect(page.locator("text=Alex Johnson")).toBeVisible();
  });

  test("roster shows all active members", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Members" }).click();
    await expect(page.locator("text=Alex Johnson")).toBeVisible();
    await expect(page.locator("text=Marcus Lee")).toBeVisible();
    await expect(page.locator("text=Jake Rivera")).toBeVisible();
    await expect(page.locator("text=Tyler Smith")).toBeVisible();
    await expect(page.locator("text=Chris Nguyen")).toBeVisible();
    await expect(page.locator("text=Devon Park")).toBeVisible();
  });
});
