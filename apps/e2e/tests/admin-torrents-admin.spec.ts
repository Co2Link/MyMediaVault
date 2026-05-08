import { expect, test } from "@playwright/test";
import { connectMongo, disconnectMongo, TorrentModel, VideoModel } from "@mymediavault/core/db";

test.afterAll(async () => {
  await disconnectMongo();
});

test("admin users can delete torrents and their videos", async ({ page }) => {
  const infoHash = `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb${Date.now().toString(16).padStart(8, "0").slice(-8)}`;
  const title = `Admin Torrent ${Date.now()}`;

  await page.goto("/add");
  await page.getByLabel("Info hash").fill(infoHash);
  await page.getByLabel("Title").fill(title);
  await page.locator("form").getByRole("button", { name: "Add video" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();

  await page.getByRole("link", { name: "Torrents" }).click();
  await expect(page.getByRole("heading", { name: "Torrent management" })).toBeVisible();

  const torrentItem = page.getByRole("listitem").filter({ hasText: infoHash });
  await expect(torrentItem).toBeVisible();
  await torrentItem.getByRole("button", { name: "Delete torrent" }).click();
  await expect(torrentItem).toHaveCount(0);

  await connectMongo();
  await expect(VideoModel.findOne({ title }).lean().exec()).resolves.toBeNull();
  await expect(TorrentModel.findOne({ infoHash }).lean().exec()).resolves.toBeNull();
});
