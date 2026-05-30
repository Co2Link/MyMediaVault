import { expect, test } from "@playwright/test";

test("standard user can add a video for metadata processing", async ({ page }) => {
  const uniqueInfoHash = `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa${Date.now().toString(16).padStart(8, "0").slice(-8)}`;
  const title = `Fixture Movie ${uniqueInfoHash.slice(-8)}`;
  await page.goto("/");
  await page.getByRole("link", { name: "Add video" }).click();
  await page.getByLabel("Info hash").fill(uniqueInfoHash);
  await page.getByLabel("Title").fill(title);
  await page.locator("form").getByRole("button", { name: "Add video" }).click();
  await expect(page.getByText("Video added. Metadata processing has been queued.")).toBeVisible();
  await expect(page.getByRole("status")).toContainText(/Metadata (pending|processing|ready)/);
  await expect(page.getByRole("heading", { name: "Torrent files" })).toBeVisible();
});
