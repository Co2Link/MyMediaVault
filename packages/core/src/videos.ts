import {
  connectMongo,
  TagModel,
  TorrentMetadataJobModel,
  TorrentModel,
  VideoModel,
  VideoTagModel,
  type TagDoc,
  type TorrentDoc,
  type TorrentMetadataJobDoc,
  type VideoDoc,
  type VideoTagDoc,
} from "./db.js";
import { getTorrentEnv } from "./env.js";
import { ConflictError, NotFoundError } from "./errors.js";
import { buildBlobStore } from "./storage.js";
import { buildTorrentProvider, type TorrentMetadata } from "./torrent-provider.js";
import type {
  PreviewDiagnosticsRead,
  PreviewFrameRead,
  PreviewRead,
  PreviewSheetRead,
  TagRead,
  TorrentFileRead,
  TorrentSummary,
  VideoDetail,
  VideoSummary,
} from "./types.js";
import { normalizeInfoHash } from "./validation.js";

type VideoRecord = {
  video: VideoDoc;
  torrent: TorrentDoc;
  tags: TagDoc[];
};

export async function searchVideos(userId: string, query?: string) {
  await connectMongo();
  const normalizedQuery = query?.trim().toLowerCase();
  const videos = (await VideoModel.find({ userId }).lean().exec()).sort(compareNewestVideoFirst);
  const records = await hydrateVideos(videos);

  return records
    .filter((record) => {
      if (!normalizedQuery) {
        return true;
      }
      return [record.video.title, record.video.description, record.torrent.name, record.torrent.infoHash].some((value) =>
        value?.toLowerCase().includes(normalizedQuery),
      );
    })
    .map(toVideoSummary);
}

export async function getVideoById(userId: string, videoId: string) {
  await connectMongo();
  const video = await VideoModel.findOne({ _id: videoId, userId }).lean().exec();
  if (!video) {
    throw new NotFoundError("Video was not found.");
  }
  return toVideoDetail(await hydrateVideo(video));
}

export async function getVideoPreviewArtifact(
  userId: string,
  videoId: string,
  artifact: "sheet" | { frameIndex: number },
) {
  await connectMongo();
  const video = await VideoModel.findOne({ _id: videoId, userId }).lean().exec();
  if (!video) {
    throw new NotFoundError("Video was not found.");
  }

  const torrent = await TorrentModel.findById(video.torrentId).lean().exec();
  if (!torrent) {
    throw new NotFoundError("Torrent was not found.");
  }

  const key =
    artifact === "sheet"
      ? torrent.previewSheet?.key
      : torrent.previewFrames.at(artifact.frameIndex)?.key;
  if (!key) {
    throw new NotFoundError("Preview artifact was not found.");
  }

  const bytes = await buildBlobStore().getBytes(key);
  return {
    bytes,
    key,
    mimeType: artifact === "sheet" ? (torrent.previewSheet?.mimeType ?? "image/jpeg") : "image/jpeg",
  };
}

export async function listTorrents() {
  await connectMongo();
  const torrents = (await TorrentModel.find().lean().exec()) as TorrentDoc[];
  const torrentIds = torrents.map((torrent) => torrent._id);
  const counts =
    torrentIds.length > 0
      ? ((await VideoModel.aggregate<{ _id: string; videoCount: number }>([
          { $match: { torrentId: { $in: torrentIds } } },
          { $group: { _id: "$torrentId", videoCount: { $sum: 1 } } },
        ]).exec()) as Array<{ _id: string; videoCount: number }>)
      : [];
  const countsByTorrentId = new Map(counts.map((entry) => [entry._id, entry.videoCount]));

  return torrents.sort(compareNewestTorrentFirst).map((torrent) => toTorrentSummary(torrent, countsByTorrentId.get(torrent._id) ?? 0));
}

export async function createVideo(
  userId: string,
  input: { infoHash: string; title: string | null; description: string | null; rating: number | null; tagIds: string[] },
) {
  await connectMongo();
  const infoHash = normalizeInfoHash(input.infoHash);
  let torrent = (await TorrentModel.findOne({ infoHash }).lean().exec()) as TorrentDoc | null;

  if (!torrent) {
    const createdTorrent = await TorrentModel.create({ infoHash, metadataStatus: "pending" });
    torrent = createdTorrent.toObject() as TorrentDoc;
  }

  const existing = await VideoModel.findOne({ userId, torrentId: torrent._id }).select({ _id: 1 }).lean().exec();
  if (existing) {
    await enqueueTorrentMetadata(torrent._id);
    throw new ConflictError("This video is already in your collection.");
  }

  const tagIds = await resolveTagIds(input.tagIds);

  try {
    const created = await VideoModel.create({
      userId,
      torrentId: torrent._id,
      title: input.title,
      description: input.description,
      rating: input.rating,
    });
    await syncVideoTags(created._id, tagIds);
    await enqueueTorrentMetadata(torrent._id);
    return toVideoDetail(await hydrateVideo(created.toObject()));
  } catch (error) {
    if (isDuplicateKeyError(error)) {
      await enqueueTorrentMetadata(torrent._id);
      throw new ConflictError("This video is already in your collection.");
    }
    throw error;
  }
}

export async function updateVideo(
  userId: string,
  videoId: string,
  input: { title: string | null; description: string | null; rating: number | null; tagIds: string[] },
) {
  await connectMongo();
  const tagIds = await resolveTagIds(input.tagIds);
  const updated = await VideoModel.findOneAndUpdate(
    { _id: videoId, userId },
    {
      $set: {
        title: input.title,
        description: input.description,
        rating: input.rating,
      },
    },
    { new: true },
  )
    .lean()
    .exec();
  if (!updated) {
    throw new NotFoundError("Video was not found.");
  }
  await syncVideoTags(updated._id, tagIds);
  return toVideoDetail(await hydrateVideo(updated));
}

export async function deleteVideo(userId: string, videoId: string) {
  await connectMongo();
  const video = await VideoModel.findOne({ _id: videoId, userId }).lean().exec();
  if (!video) {
    throw new NotFoundError("Video was not found.");
  }

  await Promise.all([
    VideoTagModel.deleteMany({ videoId: video._id }).exec(),
    VideoModel.deleteOne({ _id: video._id, userId }).exec(),
  ]);

  const remainingVideos = await VideoModel.countDocuments({ torrentId: video.torrentId }).exec();
  if (remainingVideos === 0) {
    const torrent = await TorrentModel.findById(video.torrentId).lean().exec();
    if (torrent) {
      await deleteTorrentRecord(torrent, []);
    }
  }
}

export async function deleteTorrent(torrentId: string) {
  await connectMongo();
  const torrent = await TorrentModel.findById(torrentId).lean().exec();
  if (!torrent) {
    throw new NotFoundError("Torrent was not found.");
  }

  const videos = (await VideoModel.find({ torrentId }).lean().exec()) as VideoDoc[];
  await deleteTorrentRecord(torrent, videos.map((video) => video._id));
}

export async function enqueueTorrentMetadata(torrentId: string) {
  await connectMongo();
  const torrent = await TorrentModel.findById(torrentId).lean().exec();
  if (!torrent) {
    throw new NotFoundError("Torrent was not found.");
  }
  if (torrent.metadataStatus === "succeeded" && torrent.rawBlobKey) {
    return null;
  }

  let job = (
    await TorrentMetadataJobModel.find({ torrentId, status: { $in: ["queued", "processing"] } }).lean().exec()
  ).sort(compareNewestJobFirst)[0];

  if (!job) {
    await TorrentModel.updateOne({ _id: torrentId }, { $set: { metadataStatus: "pending", metadataError: null } }).exec();
    const created = await TorrentMetadataJobModel.create({
      torrentId,
      status: "queued",
      attempt: torrent.metadataAttempts + 1,
    });
    job = created.toObject();
  }

  return job;
}

export async function claimNextTorrentMetadataJob(now = new Date()) {
  await connectMongo();
  const job = await TorrentMetadataJobModel.findOneAndUpdate(
    { status: "queued" },
    {
      $set: {
        status: "processing",
        error: null,
        lastDequeuedAt: now,
      },
    },
    {
      new: true,
      sort: { createdAt: 1, _id: 1 },
    },
  )
    .lean()
    .exec();

  return job as TorrentMetadataJobDoc | null;
}

export async function processPendingTorrentMetadataJobs(limit = 10) {
  let processed = 0;
  while (processed < limit) {
    const job = await claimNextTorrentMetadataJob();
    if (!job) {
      break;
    }
    await processTorrentMetadataJob(job._id);
    processed += 1;
  }
  return { processed };
}

export async function processTorrentMetadataJob(jobId: string) {
  await connectMongo();
  const now = new Date();
  const job = await TorrentMetadataJobModel.findById(jobId).lean().exec();
  if (!job) {
    throw new NotFoundError("Torrent processing job was not found.");
  }
  if (isFinalJobStatus(job.status)) {
    return { status: "skipped" as const, jobId };
  }

  const torrent = await TorrentModel.findById(job.torrentId).lean().exec();
  if (!torrent) {
    throw new NotFoundError("Torrent was not found.");
  }

  await Promise.all([
    TorrentMetadataJobModel.updateOne(
      { _id: job._id },
      {
        $set: {
          status: "processing",
          error: null,
          lastDequeuedAt: now,
          startedAt: job.startedAt ?? now,
          finishedAt: null,
        },
      },
    ).exec(),
    TorrentModel.updateOne(
      { _id: job.torrentId },
      {
        $set: {
          metadataStatus: "processing",
          metadataAttempts: Math.max(job.attempt, 1),
          metadataLastAttemptAt: now,
        },
      },
    ).exec(),
  ]);

  const provider = buildTorrentProvider();
  const blobStore = buildBlobStore();
  let metadata: TorrentMetadata;

  try {
    metadata = await provider.fetch(torrent.infoHash);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to resolve torrent metadata.";
    await markTorrentMetadataFailed(job._id, torrent._id, message);
    return { status: "failed" as const, jobId };
  }

  const blobKey = `torrents/${torrent.infoHash}.torrent`;
  await blobStore.putBytes(blobKey, metadata.raw);

  await Promise.all([
    TorrentModel.updateOne(
      { _id: torrent._id },
      {
        $set: {
          name: metadata.name,
          sizeBytes: metadata.sizeBytes,
          rawBlobKey: blobKey,
          metadataStatus: "succeeded",
          metadataError: null,
          files: metadata.files.map((file, index) => ({
            path: file.path,
            sizeBytes: file.sizeBytes,
            position: index,
          })),
        },
      },
    ).exec(),
    TorrentMetadataJobModel.updateOne(
      { _id: job._id },
      {
        $set: {
          status: "succeeded",
          error: null,
          finishedAt: new Date(),
        },
      },
    ).exec(),
  ]);

  return { status: "succeeded" as const, jobId };
}

export async function repairStaleTorrentMetadataJobs(now = new Date()) {
  await connectMongo();
  const env = getTorrentEnv();
  const processingBefore = new Date(now.getTime() - env.torrentRepairStaleProcessingMinutes * 60 * 1000);
  const jobs = (
    await TorrentMetadataJobModel.find({
      $or: [
        { status: "processing", $or: [{ lastDequeuedAt: null }, { lastDequeuedAt: { $lt: processingBefore } }] },
      ],
    })
      .lean()
      .exec()
  )
    .sort(compareOldestJobFirst)
    .slice(0, 25);

  for (const job of jobs) {
    await TorrentMetadataJobModel.updateOne(
      { _id: job._id },
      { $set: { status: "queued", error: null, queueEnqueuedAt: now } },
    ).exec();
  }

  return { repaired: jobs.length };
}

async function markTorrentMetadataFailed(jobId: string, torrentId: string, message: string) {
  await Promise.all([
    TorrentModel.updateOne(
      { _id: torrentId },
      {
        $set: {
          metadataStatus: "failed",
          metadataError: message,
        },
      },
    ).exec(),
    TorrentMetadataJobModel.updateOne(
      { _id: jobId },
      {
        $set: {
          status: "failed",
          error: message,
          finishedAt: new Date(),
        },
      },
    ).exec(),
  ]);
}

async function hydrateVideos(videos: VideoDoc[]): Promise<VideoRecord[]> {
  const torrentIds = [...new Set(videos.map((video) => video.torrentId))];
  const videoIds = videos.map((video) => video._id);
  const [torrentDocs, videoTagDocs] = await Promise.all([
    TorrentModel.find({ _id: { $in: torrentIds } }).lean().exec(),
    VideoTagModel.find({ videoId: { $in: videoIds } }).lean().exec(),
  ]);
  const torrents = torrentDocs as TorrentDoc[];
  const videoTags = videoTagDocs as VideoTagDoc[];
  const tagIds = [...new Set(videoTags.map((videoTag) => videoTag.tagId))];
  const tags =
    tagIds.length > 0 ? ((await TagModel.find({ _id: { $in: tagIds } }).lean().exec()) as TagDoc[]) : [];
  const torrentsById = new Map(torrents.map((torrent) => [torrent._id, torrent]));
  const tagsById = new Map(tags.map((tag) => [tag._id, tag]));
  const videoTagsByVideoId = groupVideoTags(videoTags);

  return videos.flatMap((video) => {
    const torrent = torrentsById.get(video.torrentId);
    if (!torrent) {
      return [];
    }
    const tagsForVideo = (videoTagsByVideoId.get(video._id) ?? [])
      .map((videoTag) => tagsById.get(videoTag.tagId))
      .filter((tag): tag is TagDoc => Boolean(tag))
      .sort((a, b) => a.name.localeCompare(b.name));
    return [{ video, torrent, tags: tagsForVideo }];
  });
}

async function hydrateVideo(video: VideoDoc) {
  const [record] = await hydrateVideos([video]);
  if (!record) {
    throw new NotFoundError("Video was not found.");
  }
  return record;
}

async function resolveTagIds(tagIds: string[]) {
  const uniqueTagIds = [...new Set(tagIds.map((tagId) => tagId.trim()).filter(Boolean))];
  if (uniqueTagIds.length === 0) {
    return [];
  }

  const tags = await TagModel.find({ _id: { $in: uniqueTagIds } }).select({ _id: 1 }).lean().exec();
  if (tags.length !== uniqueTagIds.length) {
    throw new NotFoundError("One or more tags were not found.");
  }

  return uniqueTagIds;
}

async function syncVideoTags(videoId: string, tagIds: string[]) {
  await VideoTagModel.deleteMany({ videoId }).exec();
  if (tagIds.length === 0) {
    return;
  }

  await VideoTagModel.create(tagIds.map((tagId) => ({ videoId, tagId })));
}

function groupVideoTags(videoTags: VideoTagDoc[]) {
  const grouped = new Map<string, VideoTagDoc[]>();
  for (const videoTag of videoTags) {
    const tags = grouped.get(videoTag.videoId) ?? [];
    tags.push(videoTag);
    grouped.set(videoTag.videoId, tags);
  }
  return grouped;
}

function isFinalJobStatus(status: string) {
  return status === "succeeded" || status === "failed";
}

function compareNewestVideoFirst(a: VideoDoc, b: VideoDoc) {
  return b.createdAt.getTime() - a.createdAt.getTime() || b._id.localeCompare(a._id);
}

function compareNewestJobFirst(a: TorrentMetadataJobDoc, b: TorrentMetadataJobDoc) {
  return b.createdAt.getTime() - a.createdAt.getTime() || b._id.localeCompare(a._id);
}

function compareNewestTorrentFirst(a: TorrentDoc, b: TorrentDoc) {
  return b.createdAt.getTime() - a.createdAt.getTime() || b._id.localeCompare(a._id);
}

function compareOldestJobFirst(a: TorrentMetadataJobDoc, b: TorrentMetadataJobDoc) {
  return a.createdAt.getTime() - b.createdAt.getTime() || a._id.localeCompare(b._id);
}

function isDuplicateKeyError(error: unknown) {
  return typeof error === "object" && error !== null && "code" in error && error.code === 11000;
}

function toVideoSummary(record: VideoRecord): VideoSummary {
  return {
    id: record.video._id,
    displayTitle: record.video.title ?? record.torrent.name,
    title: record.video.title,
    rating: record.video.rating,
    infoHash: record.torrent.infoHash,
    torrentName: record.torrent.name,
    metadataStatus: record.torrent.metadataStatus,
    preview: toPreview(record.torrent),
    tags: toTags(record),
    createdAt: record.video.createdAt.toISOString(),
    updatedAt: record.video.updatedAt.toISOString(),
  };
}

function toVideoDetail(record: VideoRecord): VideoDetail {
  return {
    ...toVideoSummary(record),
    description: record.video.description,
    sizeBytes: record.torrent.sizeBytes,
    metadataError: record.torrent.metadataError,
    files: record.torrent.files
      .slice()
      .sort((a, b) => a.position - b.position)
      .map<TorrentFileRead>((file) => ({
        path: file.path,
        sizeBytes: file.sizeBytes,
      })),
  };
}

function toTorrentSummary(torrent: TorrentDoc, videoCount: number): TorrentSummary {
  return {
    id: torrent._id,
    infoHash: torrent.infoHash,
    name: torrent.name,
    sizeBytes: torrent.sizeBytes,
    metadataStatus: torrent.metadataStatus,
    metadataError: torrent.metadataError,
    preview: toPreview(torrent),
    videoCount,
    createdAt: torrent.createdAt.toISOString(),
    updatedAt: torrent.updatedAt.toISOString(),
  };
}

function toTags(record: VideoRecord): TagRead[] {
  return record.tags.map((tag) => ({
    id: tag._id,
    name: tag.name,
  }));
}

async function deleteTorrentRecord(torrent: TorrentDoc, videoIds: string[]) {
  await Promise.all([
    videoIds.length > 0 ? VideoTagModel.deleteMany({ videoId: { $in: videoIds } }).exec() : Promise.resolve(),
    videoIds.length > 0 ? VideoModel.deleteMany({ _id: { $in: videoIds } }).exec() : Promise.resolve(),
    TorrentMetadataJobModel.deleteMany({ torrentId: torrent._id }).exec(),
    TorrentModel.deleteOne({ _id: torrent._id }).exec(),
  ]);

  const blobStore = buildBlobStore();
  const previewKeys = [
    torrent.previewSheet?.key,
    ...(torrent.previewFrames ?? []).map((frame) => frame.key),
  ].filter((key): key is string => Boolean(key));
  await Promise.all([
    torrent.rawBlobKey ? blobStore.deleteIfExists(torrent.rawBlobKey) : Promise.resolve(),
    ...previewKeys.map((key) => blobStore.deleteIfExists(key)),
  ]);
}

function toPreview(torrent: TorrentDoc): PreviewRead {
  const frames = torrent.previewFrames ?? [];
  const status = torrent.previewStatus ?? "pending";
  return {
    status,
    error: torrent.previewError ?? null,
    attempts: torrent.previewAttempts ?? 0,
    lastAttemptAt: torrent.previewLastAttemptAt?.toISOString() ?? null,
    updatedAt: torrent.previewUpdatedAt?.toISOString() ?? null,
    frames: frames.map<PreviewFrameRead>((frame) => ({
      key: frame.key,
      width: frame.width,
      height: frame.height,
      timestampSeconds: frame.timestampSeconds,
      score: frame.score,
      metadata: normalizeStringRecord(frame.metadata),
    })),
    sheet: torrent.previewSheet
      ? ({
          key: torrent.previewSheet.key,
          width: torrent.previewSheet.width,
          height: torrent.previewSheet.height,
          mimeType: torrent.previewSheet.mimeType,
          metadata: normalizeStringRecord(torrent.previewSheet.metadata),
        } satisfies PreviewSheetRead)
      : null,
    diagnostics: toPreviewDiagnostics(torrent),
  };
}

function toPreviewDiagnostics(torrent: TorrentDoc): PreviewDiagnosticsRead {
  const diagnostics = torrent.previewDiagnostics ?? {};
  return {
    artifactVersion: diagnostics.artifactVersion ?? null,
    artifactFingerprint: diagnostics.artifactFingerprint ?? null,
    downloadedBytes: diagnostics.downloadedBytes ?? null,
    elapsedSeconds: diagnostics.elapsedSeconds ?? null,
    attempts: diagnostics.attempts ?? null,
    strategyName: diagnostics.strategyName ?? null,
    selectedFilePath: diagnostics.selectedFilePath ?? null,
    selectedFileSizeBytes: diagnostics.selectedFileSizeBytes ?? null,
    failureReason: diagnostics.failureReason ?? null,
    warnings: Array.isArray(diagnostics.warnings) ? diagnostics.warnings : [],
    details: normalizeUnknownRecord(diagnostics.details),
  };
}

function normalizeStringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  );
}

function normalizeUnknownRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return { ...value };
}
