import { expect, test } from "@playwright/test";
import { fixtureInfoHash } from "../fixtures/torrents";

test("standard user can add a video and see processing status", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Add video" }).first().click();
  await page.getByLabel("Info hash").fill(fixtureInfoHash);
  await page.getByLabel("Title").fill("Fixture Movie");
  await page.locator("form").getByRole("button", { name: "Add video" }).click();
  await expect(page.getByRole("status")).toContainText(/Metadata/);
});
