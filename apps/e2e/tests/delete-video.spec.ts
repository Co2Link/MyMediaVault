import { expect, test } from "@playwright/test";
import { connectMongo, disconnectMongo, TorrentModel, VideoModel } from "@mymediavault/core/db";

test.afterAll(async () => {
  await disconnectMongo();
});

test("user can delete a video and remove the orphan torrent", async ({ page }) => {
  const infoHash = `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa${Date.now().toString(16).padStart(8, "0").slice(-8)}`;
  const title = `Delete Video ${Date.now()}`;

  await page.goto("/add");
  await page.getByLabel("Info hash").fill(infoHash);
  await page.getByLabel("Title").fill(title);
  await page.locator("form").getByRole("button", { name: "Add video" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();

  await page.getByRole("button", { name: "Delete video" }).click();
  await expect(page.getByRole("heading", { name: "Your media vault" })).toBeVisible();

  await connectMongo();
  await expect(VideoModel.findOne({ title }).lean().exec()).resolves.toBeNull();
  await expect(TorrentModel.findOne({ infoHash }).lean().exec()).resolves.toBeNull();
});
