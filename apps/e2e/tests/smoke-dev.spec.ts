import { expect, test } from "@playwright/test";
import {
  connectMongo,
  disconnectMongo,
  TorrentMetadataJobModel,
  TorrentModel,
  UserModel,
  VideoModel,
} from "@mymediavault/core/db";
import { buildBlobStore } from "@mymediavault/core/storage";
import { liveResolverInfoHash } from "../fixtures/torrents";
import { requireEnv } from "./auth-helpers";

test.afterAll(async () => {
  await disconnectMongo();
});

test("dev smoke verifies web, Cosmos DB, worker job, R2 storage, and ready metadata", async ({ page }) => {
  test.setTimeout(240_000);

  const userEmail = requireEnv("E2E_USER_USERNAME");
  const userName = userEmail.split("@")[0] ?? userEmail;
  const infoHash = (process.env.E2E_DEV_SMOKE_INFO_HASH ?? liveResolverInfoHash).toLowerCase();
  const title = `Dev Smoke ${Date.now()} ${infoHash.slice(0, 8)}`;

  await resetSmokeTorrentForUser(userEmail, userName, infoHash);

  await page.goto("/add");
  await page.getByLabel("Info hash").fill(infoHash);
  await page.getByLabel("Title").fill(title);
  await page.locator("form").getByRole("button", { name: "Add video" }).click();
  await expect(page.getByText("Video added. Metadata processing has been queued.")).toBeVisible();

  const user = await waitForDocument(
    async () => {
      await connectMongo();
      return UserModel.findOne({ $or: [{ email: userEmail }, { name: userName }] }).lean().exec();
    },
    `user ${userEmail} to exist`,
  );

  const video = await waitForDocument(
    async () => VideoModel.findOne({ userId: user._id, title }).lean().exec(),
    `video ${title} to be created`,
  );

  const torrent = await waitForDocument(
    async () => TorrentModel.findById(video.torrentId).lean().exec(),
    `torrent ${video.torrentId} to exist`,
  );

  const queuedJob = await waitForDocument(
    async () => {
      const [job] = (await TorrentMetadataJobModel.find({ torrentId: torrent._id }).lean().exec()).sort(
        (a, b) => b.createdAt.getTime() - a.createdAt.getTime() || b._id.localeCompare(a._id),
      );
      return job;
    },
    `torrent metadata job for ${torrent._id} to exist`,
  );

  expect(queuedJob.queueEnqueuedAt).not.toBeNull();

  const finishedTorrent = await waitForDocument(
    async () => {
      const current = await TorrentModel.findById(torrent._id).lean().exec();
      if (current?.metadataStatus === "failed") {
        throw new Error(`Torrent metadata failed for ${torrent._id}: ${current.metadataError ?? "unknown error"}`);
      }
      return current?.metadataStatus === "succeeded" ? current : null;
    },
    `torrent ${torrent._id} to finish processing`,
    { timeoutMs: 150_000 },
  );

  expect(finishedTorrent.rawBlobKey).toBeTruthy();
  expect(finishedTorrent.files.length).toBeGreaterThan(0);

  const finishedJob = await waitForDocument(
    async () => {
      const current = await TorrentMetadataJobModel.findById(queuedJob._id).lean().exec();
      if (current?.status === "failed" || current?.status === "dead_lettered") {
        throw new Error(`Torrent metadata job ${queuedJob._id} ended in ${current.status}: ${current.error ?? "unknown error"}`);
      }
      return current?.status === "succeeded" ? current : null;
    },
    `torrent metadata job ${queuedJob._id} to finish processing`,
    { timeoutMs: 150_000 },
  );

  expect(finishedJob.queueEnqueuedAt).not.toBeNull();
  expect(finishedJob.lastDequeuedAt).not.toBeNull();
  expect(finishedJob.startedAt).not.toBeNull();
  expect(finishedJob.finishedAt).not.toBeNull();

  const rawTorrentBytes = await buildBlobStore().getBytes(finishedTorrent.rawBlobKey!);
  expect(rawTorrentBytes.byteLength).toBeGreaterThan(0);

  await page.reload();
  await expect(page.getByRole("status")).toContainText("Metadata ready");
  await expect(page.getByRole("heading", { name: "Torrent files" })).toBeVisible();
  await expect(page.getByRole("listitem").first()).toBeVisible();
});

async function resetSmokeTorrentForUser(userEmail: string, userName: string, infoHash: string) {
  await connectMongo();
  const user = await UserModel.findOne({ $or: [{ email: userEmail }, { name: userName }] }).lean().exec();
  const torrent = await TorrentModel.findOne({ infoHash }).lean().exec();
  if (!torrent) {
    return;
  }

  if (user) {
    await VideoModel.deleteMany({ userId: user._id, torrentId: torrent._id }).exec();
  }

  const remainingVideos = await VideoModel.countDocuments({ torrentId: torrent._id }).exec();
  if (remainingVideos > 0) {
    throw new Error(
      `Cannot reset dev smoke torrent ${infoHash}; ${remainingVideos} other video(s) still reference it. Set E2E_DEV_SMOKE_INFO_HASH to another resolvable torrent.`,
    );
  }

  await Promise.all([
    TorrentMetadataJobModel.deleteMany({ torrentId: torrent._id }).exec(),
    TorrentModel.deleteOne({ _id: torrent._id }).exec(),
  ]);
}

async function waitForDocument<T>(
  query: () => Promise<T | null | undefined>,
  description: string,
  options: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<T> {
  const timeoutMs = options.timeoutMs ?? 60_000;
  const intervalMs = options.intervalMs ?? 2_000;
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown;

  while (Date.now() < deadline) {
    try {
      const result = await query();
      if (result) {
        return result;
      }
      lastError = undefined;
    } catch (error) {
      lastError = error;
    }
    await sleep(intervalMs);
  }

  if (lastError instanceof Error) {
    throw new Error(`Timed out waiting for ${description}. Last error: ${lastError.message}`);
  }
  throw new Error(`Timed out waiting for ${description}.`);
}

function sleep(milliseconds: number) {
  return new Promise<void>((resolve) => {
    setTimeout(resolve, milliseconds);
  });
}
