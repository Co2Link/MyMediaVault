import {
  ActorModel,
  connectMongo,
  TagModel,
  TorrentModel,
  VideoModel,
  VideoTagModel,
  type ActorDoc,
  type TagDoc,
  type TorrentDoc,
  type VideoDoc,
  type VideoTagDoc,
} from "./db.js";
import { resolveActorIds } from "./actors.js";
import { ConflictError, NotFoundError } from "./errors.js";
import { buildBlobStore } from "./storage.js";
import type {
  ActorAnalysisRead,
  ActorRead,
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
  actors: ActorDoc[];
  systemActors: ActorDoc[];
  userActors: ActorDoc[];
};

export async function searchVideos(userId: string, query?: string) {
  await connectMongo();
  const normalizedQuery = query?.trim().toLowerCase();
  const records = await listUserVideoRecords(userId);

  return records
    .filter((record) => {
      if (!normalizedQuery) {
        return true;
      }
      return [
        record.video.title,
        record.video.description,
        record.torrent.name,
        record.torrent.infoHash,
        ...record.tags.map((tag) => tag.name),
        ...record.actors.flatMap((actor) => [actor.name, actor.description]),
      ].some((value) => value?.toLowerCase().includes(normalizedQuery));
    })
    .map(toVideoSummary);
}

export async function listVideosByActor(userId: string, actorId: string) {
  await connectMongo();
  const records = await listUserVideoRecords(userId);
  return records
    .filter((record) => record.actors.some((actor) => actor._id === actorId))
    .map(toVideoSummary);
}

export async function listVideosByTag(userId: string, tagId: string) {
  await connectMongo();
  const records = await listUserVideoRecords(userId);
  return records
    .filter((record) => record.tags.some((tag) => tag._id === tagId))
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

export async function getTorrentPreviewArtifact(
  torrentId: string,
  artifact: "sheet" | { frameIndex: number },
) {
  await connectMongo();
  const torrent = await TorrentModel.findById(torrentId).lean().exec();
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
  input: {
    infoHash: string;
    title: string | null;
    description: string | null;
    rating: number | null;
    tagIds: string[];
    actorIds: string[];
  },
) {
  await connectMongo();
  const infoHash = normalizeInfoHash(input.infoHash);
  const actorIds = await resolveActorIds(input.actorIds);
  let torrent = (await TorrentModel.findOne({ infoHash }).lean().exec()) as TorrentDoc | null;

  if (!torrent) {
    const createdTorrent = await TorrentModel.create({ infoHash, processingState: "queued", processingQueuedAt: new Date(), processingAvailableAt: null, userActorIds: actorIds });
    torrent = createdTorrent.toObject() as TorrentDoc;
  }

  const existing = await VideoModel.findOne({ userId, torrentId: torrent._id }).select({ _id: 1 }).lean().exec();
  if (existing) {
    await ensureTorrentProcessingQueued(torrent._id);
    throw new ConflictError("This video is already in your collection.");
  }

  if (actorIds.length > 0 && !arraysEqual(actorIds, torrentUserActorIds(torrent))) {
    await TorrentModel.updateOne({ _id: torrent._id }, { $set: { userActorIds: actorIds }, $unset: { actorIds: "" } }).exec();
    torrent = { ...torrent, actorIds: undefined, userActorIds: actorIds };
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
    await ensureTorrentProcessingQueued(torrent._id);
    return toVideoDetail(await hydrateVideo(created.toObject()));
  } catch (error) {
    if (isDuplicateKeyError(error)) {
      await ensureTorrentProcessingQueued(torrent._id);
      throw new ConflictError("This video is already in your collection.");
    }
    throw error;
  }
}

export async function updateVideo(
  userId: string,
  videoId: string,
  input: { title: string | null; description: string | null; rating: number | null; tagIds: string[]; actorIds: string[] },
) {
  await connectMongo();
  const tagIds = await resolveTagIds(input.tagIds);
  const actorIds = await resolveActorIds(input.actorIds);
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
  await Promise.all([
    syncVideoTags(updated._id, tagIds),
    TorrentModel.updateOne(
      { _id: updated.torrentId },
      { $set: { userActorIds: actorIds }, $unset: { actorIds: "" } },
    ).exec(),
  ]);
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

export async function resetTorrentPreview(torrentId: string) {
  return queueTorrentProcessing(torrentId);
}

export async function cancelTorrentProcessing(torrentId: string) {
  await connectMongo();
  const result = await TorrentModel.updateOne(
    { _id: torrentId },
    {
      $set: {
        processingState: "cancelled",
        processingPhase: null,
        processingLeaseUntil: null,
        processingLastOutcome: "cancelled_by_admin",
        processingUpdatedAt: new Date(),
      },
    },
  ).exec();
  if (result.matchedCount === 0) {
    throw new NotFoundError("Torrent was not found.");
  }
}

export async function resetTorrentActorAnalysis(torrentId: string) {
  await connectMongo();
  const result = await TorrentModel.updateOne(
    { _id: torrentId },
    {
      $set: {
        actorAnalysisStatus: "pending",
        actorAnalysisAttempts: 0,
        actorAnalysisLastAttemptAt: null,
        actorAnalysisUpdatedAt: new Date(),
        actorAnalysisLeaseUntil: null,
        actorAnalysisFingerprint: null,
        actorAnalysisError: null,
        actorAnalysisDiagnostics: {},
      },
    },
  ).exec();
  if (result.matchedCount === 0) {
    throw new NotFoundError("Torrent was not found.");
  }
}

export async function queueTorrentProcessing(torrentId: string) {
  await connectMongo();
  const torrent = await TorrentModel.findById(torrentId).lean().exec();
  if (!torrent) {
    throw new NotFoundError("Torrent was not found.");
  }
  const now = new Date();
  await TorrentModel.updateOne(
    { _id: torrentId },
    {
      $set: {
        processingState: "queued",
        processingPhase: null,
        processingQueuedAt: now,
        processingAvailableAt: null,
        processingLeaseUntil: null,
        processingFailureCount: 0,
        processingLastOutcome: "queued_by_admin",
        processingLastError: null,
        processingUpdatedAt: now,
      },
    },
  ).exec();

  return { torrentId };
}

async function ensureTorrentProcessingQueued(torrentId: string) {
  const torrent = await TorrentModel.findById(torrentId).lean().exec();
  if (!torrent) {
    throw new NotFoundError("Torrent was not found.");
  }
  if (torrent.processingState === "complete" || torrent.processingState === "running") {
    return null;
  }
  return queueTorrentProcessing(torrentId);
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
  const actorIds = [...new Set(torrents.flatMap(torrentVisibleActorIds))];
  const actors =
    actorIds.length > 0 ? ((await ActorModel.find({ _id: { $in: actorIds } }).lean().exec()) as ActorDoc[]) : [];
  const torrentsById = new Map(torrents.map((torrent) => [torrent._id, torrent]));
  const tagsById = new Map(tags.map((tag) => [tag._id, tag]));
  const actorsById = new Map(actors.map((actor) => [actor._id, actor]));
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
    const actorsForVideo = mapActors(torrentVisibleActorIds(torrent), actorsById);
    const systemActorsForVideo = mapActors(torrent.systemActorIds ?? [], actorsById);
    const userActorsForVideo = mapActors(torrentUserActorIds(torrent), actorsById);
    return [
      {
        video,
        torrent,
        tags: tagsForVideo,
        actors: actorsForVideo,
        systemActors: systemActorsForVideo,
        userActors: userActorsForVideo,
      },
    ];
  });
}

async function listUserVideoRecords(userId: string) {
  const videos = (await VideoModel.find({ userId }).lean().exec()).sort(compareNewestVideoFirst);
  return hydrateVideos(videos);
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

function mapActors(actorIds: string[], actorsById: Map<string, ActorDoc>) {
  return actorIds
    .map((actorId) => actorsById.get(actorId))
    .filter((actor): actor is ActorDoc => Boolean(actor))
    .sort(compareActorNames);
}

function torrentUserActorIds(torrent: TorrentDoc) {
  return torrent.userActorIds ?? torrent.actorIds ?? [];
}

function torrentVisibleActorIds(torrent: TorrentDoc) {
  return [...new Set([...(torrent.systemActorIds ?? []), ...torrentUserActorIds(torrent)])];
}

function compareNewestVideoFirst(a: VideoDoc, b: VideoDoc) {
  return b.createdAt.getTime() - a.createdAt.getTime() || b._id.localeCompare(a._id);
}

function compareNewestTorrentFirst(a: TorrentDoc, b: TorrentDoc) {
  return b.createdAt.getTime() - a.createdAt.getTime() || b._id.localeCompare(a._id);
}

function compareActorNames(a: ActorDoc, b: ActorDoc) {
  return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
}

function isDuplicateKeyError(error: unknown) {
  return typeof error === "object" && error !== null && "code" in error && error.code === 11000;
}

function arraysEqual(left: string[], right: string[]) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function toVideoSummary(record: VideoRecord): VideoSummary {
  return {
    id: record.video._id,
    displayTitle: record.video.title ?? record.torrent.name,
    title: record.video.title,
    rating: record.video.rating,
    infoHash: record.torrent.infoHash,
    torrentName: record.torrent.name,
    processingState: record.torrent.processingState,
    preview: toPreview(record.torrent),
    tags: toTags(record),
    actors: toActors(record),
    createdAt: record.video.createdAt.toISOString(),
    updatedAt: record.video.updatedAt.toISOString(),
  };
}

function toVideoDetail(record: VideoRecord): VideoDetail {
  return {
    ...toVideoSummary(record),
    description: record.video.description,
    sizeBytes: record.torrent.sizeBytes,
    processingError: record.torrent.processingLastError,
    files: record.torrent.files
      .slice()
      .sort((a, b) => a.position - b.position)
      .map<TorrentFileRead>((file) => ({
        path: file.path,
        sizeBytes: file.sizeBytes,
      })),
    systemActors: toActorReads(record.systemActors),
    userActors: toActorReads(record.userActors),
  };
}

function toTorrentSummary(torrent: TorrentDoc, videoCount: number): TorrentSummary {
  return {
    id: torrent._id,
    infoHash: torrent.infoHash,
    name: torrent.name,
    sizeBytes: torrent.sizeBytes,
    processingState: torrent.processingState,
    processingError: torrent.processingLastError,
    preview: toPreview(torrent),
    actorAnalysis: toActorAnalysis(torrent),
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

function toActors(record: VideoRecord): ActorRead[] {
  return toActorReads(record.actors);
}

function toActorReads(actors: ActorDoc[]): ActorRead[] {
  return actors.map((actor) => ({
    id: actor._id,
    name: actor.name,
    description: actor.description,
    hasProfileImage: Boolean(actor.profileImageKey),
    profileImageSource: actor.profileImageSource ?? null,
    profileImageScore: actor.profileImageScore ?? null,
    profileImageFlags: actor.profileImageFlags ?? [],
    createdAt: actor.createdAt.toISOString(),
    updatedAt: actor.updatedAt.toISOString(),
  }));
}

function toActorAnalysis(torrent: TorrentDoc): ActorAnalysisRead {
  return {
    status: torrent.actorAnalysisStatus ?? "pending",
    attempts: torrent.actorAnalysisAttempts ?? 0,
    lastAttemptAt: torrent.actorAnalysisLastAttemptAt?.toISOString() ?? null,
    updatedAt: torrent.actorAnalysisUpdatedAt?.toISOString() ?? null,
    fingerprint: torrent.actorAnalysisFingerprint ?? null,
    error: torrent.actorAnalysisError ?? null,
    diagnostics: normalizeUnknownRecord(torrent.actorAnalysisDiagnostics),
  };
}

async function deleteTorrentRecord(torrent: TorrentDoc, videoIds: string[]) {
  await Promise.all([
    videoIds.length > 0 ? VideoTagModel.deleteMany({ videoId: { $in: videoIds } }).exec() : Promise.resolve(),
    videoIds.length > 0 ? VideoModel.deleteMany({ _id: { $in: videoIds } }).exec() : Promise.resolve(),
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
  const status = torrent.processingState ?? "queued";
  return {
    status,
    phase: torrent.processingPhase ?? null,
    failureCount: torrent.processingFailureCount ?? 0,
    lastOutcome: torrent.processingLastOutcome ?? null,
    lastError: torrent.processingLastError ?? null,
    queuedAt: torrent.processingQueuedAt?.toISOString() ?? null,
    updatedAt: torrent.processingUpdatedAt?.toISOString() ?? null,
    frames: frames.map<PreviewFrameRead>((frame) => ({
      key: frame.key,
      width: frame.width,
      height: frame.height,
      timestampSeconds: frame.timestampSeconds,
    })),
    sheet: torrent.previewSheet
      ? ({
          key: torrent.previewSheet.key,
          width: torrent.previewSheet.width,
          height: torrent.previewSheet.height,
          mimeType: torrent.previewSheet.mimeType,
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
    statusReason: diagnostics.statusReason ?? null,
    downloadedBytes: diagnostics.downloadedBytes ?? null,
    elapsedSeconds: diagnostics.elapsedSeconds ?? null,
    selectedFilePath: diagnostics.selectedFilePath ?? null,
    selectedFileSizeBytes: diagnostics.selectedFileSizeBytes ?? null,
    warnings: Array.isArray(diagnostics.warnings) ? diagnostics.warnings : [],
    details: normalizeUnknownRecord(diagnostics.details),
  };
}

function normalizeUnknownRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return { ...value };
}
