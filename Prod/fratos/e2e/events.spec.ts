import { test, expect } from "./fixtures/auth";
import { UPCOMING_EVENT_TITLE, PAST_EVENT_WITH_ATTENDANCE } from "./test-data";

test.describe("Events", () => {
  test("officer can view event list", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await expect(page.locator("h1", { hasText: "Events" })).toBeVisible();
    await expect(page.getByText(UPCOMING_EVENT_TITLE, { exact: true })).toBeVisible();
  });

  test("officer can toggle between upcoming and past events", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("button", { hasText: "past" }).click();
    await expect(page.getByText(PAST_EVENT_WITH_ATTENDANCE, { exact: true })).toBeVisible();
    await page.locator("button", { hasText: "upcoming" }).click();
    await expect(page.getByText(UPCOMING_EVENT_TITLE, { exact: true })).toBeVisible();
  });

  test("officer can view event detail", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.getByText(UPCOMING_EVENT_TITLE, { exact: true }).click();
    await expect(page.locator("h2", { hasText: UPCOMING_EVENT_TITLE })).toBeVisible();
    await expect(page.locator("text=Chapter House")).toBeVisible();
  });

  test("officer can create an event", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("button", { hasText: "New Event" }).click();
    await expect(page.locator("h3", { hasText: "Create Event" })).toBeVisible();

    await page.locator("input").nth(0).fill("Test Event");
    await page.locator("input[type='date']").fill("2026-05-01");
    await page.locator("input[type='time']").fill("19:00");
    await page.locator("input").nth(3).fill("Test Location");
    await page.locator("button", { hasText: "Create" }).click();

    await expect(page.getByText("Test Event", { exact: true }).first()).toBeVisible();
  });

  test("officer sees attendance roster on event detail", async ({ officerPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await page.locator("button", { hasText: "past" }).click();
    await page.getByText(PAST_EVENT_WITH_ATTENDANCE, { exact: true }).click();
    await expect(page.locator("text=Attendance")).toBeVisible();
    await expect(page.getByText("Present", { exact: true }).first()).toBeVisible();
  });

  test("member can view events", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await expect(page.getByText(UPCOMING_EVENT_TITLE, { exact: true })).toBeVisible();
  });

  test("member does not see New Event button", async ({ memberPage: page }) => {
    await page.locator("button", { hasText: "Events" }).click();
    await expect(page.locator("button", { hasText: "New Event" })).not.toBeVisible();
  });
});
