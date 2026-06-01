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

  await page.goto("/admin/torrents");
  await expect(page.getByRole("heading", { name: "Torrent management" })).toBeVisible();

  const torrentItem = page.getByRole("listitem").filter({ hasText: infoHash });
  await expect(torrentItem).toBeVisible();

  await connectMongo();
  await TorrentModel.updateOne(
    { infoHash },
    {
      $set: {
        previewStatus: "failed",
        previewNextAttemptAt: new Date("2026-05-31T02:15:00.000Z"),
        actorAnalysisStatus: "failed",
        actorAnalysisAttempts: 3,
        actorAnalysisError: "Actor analysis failed.",
      },
    },
  ).exec();
  await page.reload();
  await torrentItem.getByText("Preview: failed").click();
  await expect(torrentItem.getByText("Next attempt")).toBeVisible();
  await expect(torrentItem.getByText("5/31/2026, 2:15:00 AM")).toBeVisible();
  await torrentItem.getByText("Actor analysis: failed").click();
  await expect(torrentItem.getByText("Actor analysis failed.")).toBeVisible();

  await torrentItem.getByRole("button", { name: "Reanalyze actors" }).click();
  await expect
    .poll(async () => (await TorrentModel.findOne({ infoHash }).lean().exec())?.actorAnalysisStatus)
    .toBe("pending");

  await torrentItem.getByRole("button", { name: "Delete torrent" }).click();
  await expect(torrentItem).toHaveCount(0);

  await expect(VideoModel.findOne({ title }).lean().exec()).resolves.toBeNull();
  await expect(TorrentModel.findOne({ infoHash }).lean().exec()).resolves.toBeNull();
});
