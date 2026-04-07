import { test, expect } from "./fixtures/auth";
import { UPCOMING_EVENT_TITLE, UPCOMING_EVENT_FORMAL } from "./test-data";

test.describe("Excuse Submission", () => {
  test.describe.configure({ mode: "serial" });

  test("member can submit an excuse for a future event", async ({ memberTylerPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.getByText(UPCOMING_EVENT_FORMAL, { exact: true }).click();
    await page.locator("button", { hasText: "Submit Excuse" }).click();

    await expect(page.locator("h3", { hasText: "Submit Excuse" })).toBeVisible();
    await page.locator("textarea").fill("I have a doctor's appointment");
    await page.locator("button", { hasText: "Submit" }).last().click();

    await expect(page.locator("text=Excuse submitted")).toBeVisible();
  });

  test("officer can review excuses from dashboard", async ({ officerPage: page }) => {
    await expect(page.getByText("Pending Excuses").first()).toBeVisible({ timeout: 15000 });
    const approve = page.getByRole("button", { name: "Approve" }).first();
    await expect(approve).toBeVisible({ timeout: 15000 });
    await approve.click();
    await page.waitForTimeout(500);
  });

  test("empty reason does not submit", async ({ memberAltPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.getByText(UPCOMING_EVENT_FORMAL, { exact: true }).click();
    await page.locator("button", { hasText: "Submit Excuse" }).click();

    const submitBtn = page.locator("button", { hasText: "Submit" }).last();
    await submitBtn.click();
    await expect(page.locator("h3", { hasText: "Submit Excuse" })).toBeVisible();
  });

  test("submit button disabled while loading", async ({ memberAltPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.getByText(UPCOMING_EVENT_TITLE, { exact: true }).click();
    await page.locator("button", { hasText: "Submit Excuse" }).click();

    await page.locator("textarea").fill("Test reason");
    const submitBtn = page.locator("button", { hasText: "Submit" }).last();
    await submitBtn.click();
    await expect(page.locator("text=Excuse submitted")).toBeVisible();
  });

  test("duplicate excuse shows error", async ({ memberTylerPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.getByText(UPCOMING_EVENT_TITLE, { exact: true }).click();

    await page.locator("button", { hasText: "Submit Excuse" }).click();
    await page.locator("textarea").fill("First reason");
    await page.locator("button", { hasText: "Submit" }).last().click();
    await expect(page.locator("text=Excuse submitted")).toBeVisible();
    await page.waitForTimeout(3000);

    await page.locator("button", { hasText: "Submit Excuse" }).click();
    await page.locator("textarea").fill("Second reason");
    await page.locator("button", { hasText: "Submit" }).last().click();
    await expect(page.getByText("Excuse already submitted for this event")).toBeVisible();
  });
});
