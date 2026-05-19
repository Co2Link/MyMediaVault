import { expect, test } from "@playwright/test";
import { liveResolverInfoHash } from "../fixtures/torrents.js";

test("standard user can add a video and see processing status", async ({ page }) => {
  const uniqueInfoHash = `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa${Date.now().toString(16).padStart(8, "0").slice(-8)}`;
  await page.goto("/");
  await page.getByRole("link", { name: "Add video" }).click();
  await page.getByLabel("Info hash").fill(uniqueInfoHash);
  await page.getByLabel("Title").fill("Fixture Movie");
  await page.locator("form").getByRole("button", { name: "Add video" }).click();
  await expect(page.getByText("Video added. Metadata processing has been queued.")).toBeVisible();
  await expect(page.getByRole("status")).toContainText(/Metadata (pending|processing|ready)/);
});

test("standard user can add a live torrent and wait for metadata completion @manual-torrent", async ({ page }) => {
  test.setTimeout(180_000);

  const title = `Live Torrent ${liveResolverInfoHash.slice(0, 8)}`;
  await page.goto("/");
  await page.getByRole("link", { name: "Add video" }).click();
  await page.getByLabel("Info hash").fill(liveResolverInfoHash);
  await page.getByLabel("Title").fill(title);
  await page.locator("form").getByRole("button", { name: "Add video" }).click();
  const createdMessage = page.getByText("Video added. Metadata processing has been queued.");
  const duplicateMessage = page.getByText("This video is already in your collection.");
  const outcome = await Promise.race([
    page.waitForURL(/\/videos\/.+\?created=1$/, { timeout: 10_000 }).then(() => "created" as const),
    duplicateMessage.waitFor({ state: "visible", timeout: 10_000 }).then(() => "duplicate" as const),
  ]);

  if (outcome === "created") {
    await expect(createdMessage).toBeVisible();
    await expect(page.getByRole("status")).toContainText(/Metadata (pending|processing|ready)/);
  } else {
    await expect(duplicateMessage).toBeVisible();
  }

  for (let attempt = 0; attempt < 30; attempt += 1) {
    await page.getByRole("link", { name: "Collection" }).click();
    await page.getByLabel("Search videos").fill(liveResolverInfoHash);
    await page.getByLabel("Search videos").press("Enter");

    const item = page.locator("section.content-grid > article").first();
    await expect(item).toBeVisible({ timeout: 10_000 });

    const status = item.getByRole("status");
    const statusText = await status.textContent();
    if (statusText?.includes("Metadata ready")) {
      await item.getByRole("link", { name: "View details" }).click();
      await expect(page.getByRole("status")).toContainText("Metadata ready");
      await expect(page.getByRole("heading", { name: "Torrent files" })).toBeVisible({ timeout: 10_000 });
      await expect(page.getByRole("listitem").first()).toBeVisible({ timeout: 10_000 });
      return;
    }

    if (statusText?.includes("Metadata failed")) {
      throw new Error(`Metadata fetch failed for live hash ${liveResolverInfoHash}`);
    }

    await page.waitForTimeout(5_000);
  }

  throw new Error(`Timed out waiting for metadata completion for ${liveResolverInfoHash}`);
});
