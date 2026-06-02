import { expect, test } from "@playwright/test";
import {
  connectMongo,
  disconnectMongo,
  type TorrentDoc,
  TorrentModel,
  UserModel,
  VideoModel,
  VideoTagModel,
} from "@mymediavault/core/db";
import { buildBlobStore } from "@mymediavault/core/storage";
import { liveResolverInfoHash } from "../fixtures/torrents.js";
import { requireEnv } from "./auth-helpers.js";

test.afterAll(async () => {
  await disconnectMongo();
});

test("dev smoke verifies web, Cosmos DB, VM worker, R2 storage, preview, and cleanup", async ({ page }) => {
  test.setTimeout(900_000);

  const userEmail = requireEnv("E2E_USER_USERNAME");
  const userName = userEmail.split("@")[0] ?? userEmail;
  const infoHash = (process.env.E2E_DEV_SMOKE_INFO_HASH ?? liveResolverInfoHash).toLowerCase();
  const title = `Dev Smoke ${Date.now()} ${infoHash.slice(0, 8)}`;

  await resetSmokeTorrentForUser(userEmail, userName, infoHash);

  let torrentId: string | null = null;
  let userId: string | null = null;
  let previewKeys: string[] = [];
  try {
    await page.goto("/add");
    await page.getByLabel("Info hash").fill(infoHash);
    await page.getByLabel("Title").fill(title);
    await page.locator("form").getByRole("button", { name: "Add video" }).click();
    await expect(page.getByText("Video added. Preview processing has been queued.")).toBeVisible();

    const user = await waitForDocument(
      async () => {
        await connectMongo();
        return UserModel.findOne({ $or: [{ email: userEmail }, { name: userName }] }).lean().exec();
      },
      `user ${userEmail} to exist`,
    );
    userId = user._id;

    const video = await waitForDocument(
      async () => VideoModel.findOne({ userId: user._id, title }).lean().exec(),
      `video ${title} to be created`,
    );

    const torrent = await waitForDocument(
      async () => TorrentModel.findById(video.torrentId).lean().exec(),
      `torrent ${video.torrentId} to exist`,
    );
    torrentId = torrent._id;

    expect(["pending", "processing", "succeeded"]).toContain(torrent.metadataStatus);

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
    expect(finishedTorrent.metadataAttempts).toBeGreaterThan(0);
    expect(finishedTorrent.metadataLastAttemptAt).not.toBeNull();
    expect(finishedTorrent.metadataFinishedAt).not.toBeNull();

    const rawTorrentBytes = await buildBlobStore().getBytes(finishedTorrent.rawBlobKey!);
    expect(rawTorrentBytes.byteLength).toBeGreaterThan(0);

    const previewedTorrent = await waitForDocument(
      async () => {
        const current = await TorrentModel.findById(torrent._id).lean().exec();
        if (current?.previewStatus === "failed") {
          throw new Error(
            `Torrent preview degraded for ${torrent._id}: ${current.previewStatus} ${current.previewDiagnostics?.statusReason ?? ""}`,
          );
        }
        if (
          (current?.previewStatus === "succeeded" || current?.previewStatus === "partial") &&
          (current.previewSheet || (current.previewFrames ?? []).length > 0)
        ) {
          return current;
        }
        return null;
      },
      `torrent ${torrent._id} to finish preview generation`,
      { timeoutMs: Number(process.env.E2E_DEV_SMOKE_PREVIEW_TIMEOUT_MS ?? "600000"), intervalMs: 10_000 },
    );

    expect(previewedTorrent.previewSheet?.key).toBeTruthy();
    expect(previewedTorrent.previewFrames.length).toBeGreaterThan(0);
    expect(previewedTorrent.previewDiagnostics.artifactVersion).toBeTruthy();
    expect(previewedTorrent.previewDiagnostics.artifactFingerprint).toBeTruthy();
    previewKeys = previewBlobKeys(previewedTorrent);

    const previewSheetBytes = await buildBlobStore().getBytes(previewedTorrent.previewSheet!.key);
    expect(previewSheetBytes.byteLength).toBeGreaterThan(0);
    const firstFrameBytes = await buildBlobStore().getBytes(previewedTorrent.previewFrames[0]!.key);
    expect(firstFrameBytes.byteLength).toBeGreaterThan(0);

    await page.reload();
    await expect(page.getByRole("status")).toContainText("Metadata ready");
    const previewDisclosure = page.getByText("Torrent preview");
    await expect(previewDisclosure).toBeVisible();
    const previewSheet = page.getByAltText("Torrent preview sheet");
    if (!(await previewSheet.isVisible())) {
      await previewDisclosure.click();
    }
    await expect(previewSheet).toBeVisible();
    await expect(page.getByAltText(/^Torrent preview frame /).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Torrent files" })).toBeVisible();
    await expect(page.getByRole("listitem").first()).toBeVisible();

    await page.getByRole("link", { name: "Collection" }).click();
    await page.getByLabel("Search videos").fill(title);
    await page.getByLabel("Search videos").press("Enter");
    const card = page.locator("section.content-grid > article").first();
    const previewImageTotal = 1 + previewedTorrent.previewFrames.length;
    await expect(card.getByAltText("Torrent preview sheet")).toBeVisible();
    await expect(card.getByText(`1/${previewImageTotal}`)).toBeVisible();
    await card.getByRole("button", { name: "Next preview image" }).click();
    await expect(card.getByText(`2/${previewImageTotal}`)).toBeVisible();
    await card.getByRole("button", { name: "Previous preview image" }).click();
    await expect(card.getByText(`1/${previewImageTotal}`)).toBeVisible();
    await card.getByRole("button", { name: "Open full size preview" }).click();
    const lightbox = page.getByRole("dialog", { name: "Full size preview image" });
    await expect(lightbox).toBeVisible();
    await lightbox.getByRole("button", { name: "Next preview image" }).click();
    await expect(lightbox.getByText(`2/${previewImageTotal}`)).toBeVisible();
    await lightbox.getByRole("button", { name: "Previous preview image" }).click();
    await expect(lightbox.getByText(`1/${previewImageTotal}`)).toBeVisible();
    await lightbox.getByRole("button", { name: "Close full size preview" }).click();
  } finally {
    await cleanupSmokeTorrent(userId, torrentId, previewKeys);
  }
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
    await requeuePreviewIfNeeded(torrent._id);
    return;
  }

  const keys = torrentBlobKeys(torrent);
  await Promise.all([
    TorrentModel.deleteOne({ _id: torrent._id }).exec(),
  ]);
  await deleteBlobKeys(keys);
}

async function cleanupSmokeTorrent(userId: string | null, torrentId: string | null, observedPreviewKeys: string[]) {
  if (!torrentId) {
    return;
  }

  await connectMongo();
  const torrent = await TorrentModel.findById(torrentId).lean().exec();
  const keys = [...new Set([...torrentBlobKeys(torrent), ...observedPreviewKeys])];

  if (userId) {
    const videos = await VideoModel.find({ userId, torrentId }).select({ _id: 1 }).lean().exec();
    await VideoModel.deleteMany({ userId, torrentId }).exec();
    if (videos.length > 0) {
      await VideoTagModel.deleteMany({ videoId: { $in: videos.map((video) => video._id) } }).exec();
    }
  }

  const remainingVideos = await VideoModel.countDocuments({ torrentId }).exec();
  if (remainingVideos === 0) {
    await TorrentModel.deleteOne({ _id: torrentId }).exec();
    await deleteBlobKeys(keys);
  } else {
    await requeuePreviewIfNeeded(torrentId);
  }
}

async function requeuePreviewIfNeeded(torrentId: string) {
  const torrent = await TorrentModel.findById(torrentId).lean().exec();
  if (!torrent) {
    return;
  }

  const needsPreview =
    torrent.previewStatus === "processing" ||
    torrent.previewStatus === "failed" ||
    torrent.previewStatus === "partial" ||
    !torrent.previewSheet ||
    (torrent.previewFrames ?? []).length === 0;

  if (!needsPreview) {
    return;
  }

  await TorrentModel.updateOne(
    { _id: torrentId },
    {
      $set: {
        previewStatus: "pending",
        previewAttempts: 0,
        previewDiagnostics: {},
      },
    },
  ).exec();
}

async function deleteBlobKeys(keys: string[]) {
  if (keys.length === 0) {
    return;
  }
  const blobStore = buildBlobStore();
  await Promise.all([...new Set(keys)].map((key) => blobStore.deleteIfExists(key)));
}

function torrentBlobKeys(torrent: TorrentDoc | null | undefined) {
  if (!torrent) {
    return [];
  }
  return [
    torrent.rawBlobKey,
    torrent.previewSheet?.key,
    ...((torrent.previewFrames ?? []).map((frame) => frame.key)),
  ].filter((key): key is string => Boolean(key));
}

function previewBlobKeys(torrent: TorrentDoc) {
  return [
    torrent.previewSheet?.key,
    ...((torrent.previewFrames ?? []).map((frame) => frame.key)),
  ].filter((key): key is string => Boolean(key));
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
