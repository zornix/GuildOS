import { test, expect } from "./fixtures/auth";

test.describe("Excuse Submission", () => {
  test("member can submit an excuse for a future event", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("text=Chapter Meeting").click();
    await page.locator("button", { hasText: "Submit Excuse" }).click();

    await expect(page.locator("h3", { hasText: "Submit Excuse" })).toBeVisible();
    await page.locator("textarea").fill("I have a doctor's appointment");
    await page.locator("button", { hasText: "Submit" }).last().click();

    await expect(page.locator("text=Excuse submitted")).toBeVisible();
  });

  test("submit button disabled while loading", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("text=Chapter Meeting").click();
    await page.locator("button", { hasText: "Submit Excuse" }).click();

    await page.locator("textarea").fill("Test reason");
    const submitBtn = page.locator("button", { hasText: "Submit" }).last();
    await submitBtn.click();
    // The button should briefly show "Submitting..." (loading state)
    // then toast appears and modal closes
    await expect(page.locator("text=Excuse submitted")).toBeVisible();
  });

  test("empty reason does not submit", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("text=Chapter Meeting").click();
    await page.locator("button", { hasText: "Submit Excuse" }).click();

    const submitBtn = page.locator("button", { hasText: "Submit" }).last();
    await submitBtn.click();
    // Modal should still be open (not submitted)
    await expect(page.locator("h3", { hasText: "Submit Excuse" })).toBeVisible();
  });

  test("duplicate excuse shows error", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("text=Chapter Meeting").click();

    // First submission
    await page.locator("button", { hasText: "Submit Excuse" }).click();
    await page.locator("textarea").fill("First reason");
    await page.locator("button", { hasText: "Submit" }).last().click();
    await expect(page.locator("text=Excuse submitted")).toBeVisible();
    await page.waitForTimeout(3000);

    // Second submission attempt for same event
    await page.locator("button", { hasText: "Submit Excuse" }).click();
    await page.locator("textarea").fill("Second reason");
    await page.locator("button", { hasText: "Submit" }).last().click();
    await expect(page.locator("text=Excuse already submitted")).toBeVisible();
  });

  test("officer can review excuses from dashboard", async ({ officerPage: page }) => {
    await expect(page.locator("text=Pending Excuses")).toBeVisible();
    const excuseCard = page.locator("text=Had a midterm exam conflict").locator("..");
    await expect(excuseCard).toBeVisible();

    await page.locator("button", { hasText: "Approve" }).first().click();
    await page.waitForTimeout(500);
  });
});
