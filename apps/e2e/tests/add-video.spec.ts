import { expect, test } from "@playwright/test";
import { fixtureInfoHash, liveResolverInfoHash } from "../fixtures/torrents";

test("standard user can add a video and see processing status", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Add video" }).first().click();
  await page.getByLabel("Info hash").fill(fixtureInfoHash);
  await page.getByLabel("Title").fill("Fixture Movie");
  await page.locator("form").getByRole("button", { name: "Add video" }).click();
  await expect(page.getByRole("status")).toContainText(/Metadata (pending|processing|ready)/);
});

test("standard user can add a live torrent and wait for metadata completion @manual-torrent", async ({ page }) => {
  test.setTimeout(180_000);

  const title = `Live Torrent ${liveResolverInfoHash.slice(0, 8)}`;
  await page.goto("/");
  await page.getByRole("button", { name: "Add video" }).first().click();
  await page.getByLabel("Info hash").fill(liveResolverInfoHash);
  await page.getByLabel("Title").fill(title);
  await page.locator("form").getByRole("button", { name: "Add video" }).click();
  await expect(page.getByRole("status")).toContainText(/Metadata (pending|processing|ready)/);

  for (let attempt = 0; attempt < 30; attempt += 1) {
    await page.getByRole("button", { name: "Collection" }).click();
    await page.getByLabel("Search videos").fill(title);
    await page.getByLabel("Search videos").press("Enter");

    const item = page.locator("article").filter({ hasText: title }).first();
    await expect(item).toBeVisible({ timeout: 10_000 });

    const status = item.getByRole("status");
    const statusText = await status.textContent();
    if (statusText?.includes("Metadata ready")) {
      await item.getByRole("button", { name: "View details" }).click();
      await expect(page.getByRole("status")).toContainText("Metadata ready");
      await expect(page.locator("article ul li").first()).toBeVisible({ timeout: 10_000 });
      return;
    }

    if (statusText?.includes("Metadata failed")) {
      throw new Error(`Metadata fetch failed for live hash ${liveResolverInfoHash}`);
    }

    await page.waitForTimeout(5_000);
  }

  throw new Error(`Timed out waiting for metadata completion for ${liveResolverInfoHash}`);
});
