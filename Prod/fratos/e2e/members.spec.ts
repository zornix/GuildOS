import { test, expect } from "./fixtures/auth";
import { MEMBERS } from "./test-data";

test.describe("Members", () => {
  test("officer can view chapter roster", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Members" }).click();
    await expect(page.locator("h1", { hasText: "Members" })).toBeVisible();
    await expect(page.locator("text=Chapter Roster")).toBeVisible();
    await expect(page.getByText(MEMBERS.alex, { exact: true })).toBeVisible();
    await expect(page.getByText(MEMBERS.marcus, { exact: true })).toBeVisible();
  });

  test("officer sees role badges on members", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Members" }).click();
    const officerBadges = page.locator("text=officer");
    expect(await officerBadges.count()).toBeGreaterThanOrEqual(1);
  });

  test("member can view chapter roster", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Members" }).click();
    await expect(page.locator("text=Chapter Roster")).toBeVisible();
    await expect(page.getByText(MEMBERS.alex, { exact: true })).toBeVisible();
  });

  test("roster shows all active members", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Members" }).click();
    await expect(page.getByText(MEMBERS.officer, { exact: true }).nth(1)).toBeVisible();
    await expect(page.getByText(MEMBERS.ryan, { exact: true })).toBeVisible();
    await expect(page.getByText(MEMBERS.tyler, { exact: true })).toBeVisible();
    await expect(page.getByText(MEMBERS.marcus, { exact: true })).toBeVisible();
    await expect(page.getByText(MEMBERS.alex, { exact: true })).toBeVisible();
    await expect(page.getByText(MEMBERS.chris, { exact: true })).toBeVisible();
    await expect(page.getByText(MEMBERS.ethan, { exact: true })).toBeVisible();
    await expect(page.getByText(MEMBERS.noah, { exact: true })).toBeVisible();
  });
});
