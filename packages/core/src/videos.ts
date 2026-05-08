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
import { getEnv } from "./env.js";
import { ConflictError, NotFoundError } from "./errors.js";
import { buildBlobStore, buildQueueStore } from "./storage.js";
import { buildTorrentProvider, type TorrentMetadata } from "./torrent-provider.js";
import type { TagRead, TorrentFileRead, TorrentSummary, VideoDetail, VideoSummary } from "./types.js";
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
  let torrent = await TorrentModel.findOne({ infoHash }).lean().exec();

  if (!torrent) {
    const createdTorrent = await TorrentModel.create({ infoHash, metadataStatus: "pending" });
    torrent = createdTorrent.toObject();
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

  if (!job.queueEnqueuedAt) {
    await sendTorrentMetadataQueueMessage(job._id);
  }

  return job;
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

export function parseTorrentMetadataQueueMessage(raw: unknown) {
  const value = unwrapQueueMessage(raw);
  if (!value || typeof value !== "object") {
    throw new Error("Torrent metadata queue message must be an object.");
  }
  const message = value as { version?: unknown; jobId?: unknown };
  if (message.version !== 1 || typeof message.jobId !== "string" || !message.jobId) {
    throw new Error("Invalid torrent metadata queue message.");
  }
  return { version: 1 as const, jobId: message.jobId };
}

function unwrapQueueMessage(raw: unknown) {
  if (typeof raw === "string") {
    return JSON.parse(raw);
  }

  if (raw instanceof Uint8Array) {
    return JSON.parse(new TextDecoder().decode(raw));
  }

  if (raw && typeof raw === "object") {
    const record = raw as Record<string, unknown>;
    for (const key of ["messageText", "body", "content", "text"]) {
      const value = record[key];
      if (typeof value === "string") {
        try {
          return JSON.parse(value);
        } catch {
          return value;
        }
      }
      if (value instanceof Uint8Array) {
        return JSON.parse(new TextDecoder().decode(value));
      }
    }
  }

  return raw;
}

export async function markTorrentMetadataPoisoned(raw: unknown) {
  await connectMongo();
  const message = parseTorrentMetadataQueueMessage(raw);
  const job = await TorrentMetadataJobModel.findById(message.jobId).lean().exec();
  if (!job || isFinalJobStatus(job.status)) {
    return { status: "skipped" as const, jobId: message.jobId };
  }
  await TorrentMetadataJobModel.updateOne(
    { _id: message.jobId },
    {
      $set: {
        status: "dead_lettered",
        error: "Queue message moved to poison queue after max dequeue attempts.",
        finishedAt: new Date(),
      },
    },
  ).exec();
  return { status: "dead_lettered" as const, jobId: message.jobId };
}

export async function repairStaleTorrentMetadataJobs(now = new Date()) {
  await connectMongo();
  const env = getEnv();
  const queuedBefore = new Date(now.getTime() - env.torrentRepairStaleQueuedMinutes * 60 * 1000);
  const processingBefore = new Date(now.getTime() - env.torrentRepairStaleProcessingMinutes * 60 * 1000);
  const jobs = (
    await TorrentMetadataJobModel.find({
      $or: [
        { status: "queued", $or: [{ queueEnqueuedAt: null }, { queueEnqueuedAt: { $lt: queuedBefore } }] },
        { status: "processing", $or: [{ lastDequeuedAt: null }, { lastDequeuedAt: { $lt: processingBefore } }] },
      ],
    })
      .lean()
      .exec()
  )
    .sort(compareOldestJobFirst)
    .slice(0, 25);

  for (const job of jobs) {
    await TorrentMetadataJobModel.updateOne({ _id: job._id }, { $set: { status: "queued", error: null } }).exec();
    await sendTorrentMetadataQueueMessage(job._id);
  }

  return { repaired: jobs.length };
}

async function sendTorrentMetadataQueueMessage(jobId: string) {
  const env = getEnv();
  const queueStore = buildQueueStore();
  await queueStore.sendJson(env.torrentMetadataQueue, { version: 1, jobId });
  await TorrentMetadataJobModel.updateOne({ _id: jobId }, { $set: { queueEnqueuedAt: new Date() } }).exec();
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
  return status === "succeeded" || status === "failed" || status === "dead_lettered";
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

  if (torrent.rawBlobKey) {
    await buildBlobStore().deleteIfExists(torrent.rawBlobKey);
  }
}
