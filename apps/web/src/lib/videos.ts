import { Prisma } from "@prisma/client";
import { db } from "@/lib/db";
import { ConflictError, NotFoundError } from "@/lib/errors";
import { buildBlobStore } from "@/lib/storage";
import { buildTorrentProvider } from "@/lib/torrent-provider";
import type { TagRead, TorrentFileRead, VideoDetail, VideoSummary } from "@/lib/types";
import { normalizeInfoHash } from "@/lib/validation";

const videoInclude = {
  torrent: { include: { files: { orderBy: { position: "asc" } } } },
  videoTags: { include: { tag: true }, orderBy: { tag: { name: "asc" } } },
} satisfies Prisma.VideoInclude;

type VideoRecord = Prisma.VideoGetPayload<{ include: typeof videoInclude }>;

export async function searchVideos(userId: string, query?: string) {
  const normalizedQuery = query?.trim();
  const videos = await db.video.findMany({
    where: {
      userId,
      ...(normalizedQuery
        ? {
            OR: [
              { title: { contains: normalizedQuery } },
              { description: { contains: normalizedQuery } },
              { torrent: { name: { contains: normalizedQuery } } },
              { torrent: { infoHash: { contains: normalizedQuery } } },
            ],
          }
        : {}),
    },
    include: videoInclude,
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
  });

  return videos.map(toVideoSummary);
}

export async function getVideoById(userId: string, videoId: string) {
  const video = await db.video.findFirst({
    where: { id: videoId, userId },
    include: videoInclude,
  });
  if (!video) {
    throw new NotFoundError("Video was not found.");
  }
  return toVideoDetail(video);
}

export async function createVideo(
  userId: string,
  input: { infoHash: string; title: string | null; description: string | null; rating: number | null },
) {
  const infoHash = normalizeInfoHash(input.infoHash);
  let torrent = await db.torrent.findUnique({ where: { infoHash } });

  if (!torrent) {
    torrent = await db.torrent.create({
      data: { infoHash, metadataStatus: "pending" },
    });
  }

  const existing = await db.video.findFirst({
    where: { userId, torrentId: torrent.id },
    select: { id: true },
  });
  if (existing) {
    await enqueueTorrentMetadata(torrent.id);
    throw new ConflictError("This video is already in your collection.");
  }

  const created = await db.video.create({
    data: {
      userId,
      torrentId: torrent.id,
      title: input.title,
      description: input.description,
      rating: input.rating,
    },
    include: videoInclude,
  });

  await enqueueTorrentMetadata(torrent.id);
  return toVideoDetail(created);
}

export async function updateVideo(
  userId: string,
  videoId: string,
  input: { title: string | null; description: string | null; rating: number | null },
) {
  const existing = await db.video.findFirst({
    where: { id: videoId, userId },
    select: { id: true },
  });
  if (!existing) {
    throw new NotFoundError("Video was not found.");
  }

  const updated = await db.video.update({
    where: { id: videoId },
    data: {
      title: input.title,
      description: input.description,
      rating: input.rating,
    },
    include: videoInclude,
  });
  return toVideoDetail(updated);
}

export async function enqueueTorrentMetadata(torrentId: string) {
  const torrent = await db.torrent.findUnique({ where: { id: torrentId } });
  if (!torrent) {
    throw new NotFoundError("Torrent was not found.");
  }
  if (torrent.metadataStatus === "succeeded" && torrent.rawBlobKey) {
    return null;
  }

  const activeJob = await db.torrentProcessingJob.findFirst({
    where: {
      torrentId,
      status: { in: ["queued", "running"] },
    },
  });
  if (activeJob) {
    return activeJob;
  }

  await db.torrent.update({
    where: { id: torrentId },
    data: { metadataStatus: "pending", metadataError: null },
  });

  return db.torrentProcessingJob.create({
    data: {
      torrentId,
      status: "queued",
      attempt: torrent.metadataAttempts + 1,
    },
  });
}

export async function claimTorrentProcessingJob(workerId: string, leaseSeconds: number) {
  const now = new Date();
  const expired = new Date(now.getTime());
  const job = await db.torrentProcessingJob.findFirst({
    where: {
      OR: [
        { status: "queued" },
        {
          status: "running",
          leaseExpiresAt: { lt: expired },
        },
      ],
    },
    orderBy: [{ createdAt: "asc" }, { id: "asc" }],
  });

  if (!job) {
    return null;
  }

  const leaseExpiresAt = new Date(now.getTime() + leaseSeconds * 1000);
  return db.$transaction(async (tx) => {
    const claimed = await tx.torrentProcessingJob.update({
      where: { id: job.id },
      data: {
        status: "running",
        workerId,
        startedAt: job.startedAt ?? now,
        finishedAt: null,
        error: null,
        lastHeartbeatAt: now,
        leaseExpiresAt,
      },
    });
    await tx.torrent.update({
      where: { id: job.torrentId },
      data: {
        metadataStatus: "processing",
        metadataAttempts: Math.max(job.attempt, 1),
        metadataLastAttemptAt: now,
      },
    });
    return claimed;
  });
}

export async function heartbeatTorrentProcessingJob(jobId: string, leaseSeconds: number) {
  const now = new Date();
  const leaseExpiresAt = new Date(now.getTime() + leaseSeconds * 1000);
  await db.torrentProcessingJob.update({
    where: { id: jobId },
    data: {
      lastHeartbeatAt: now,
      leaseExpiresAt,
    },
  });
}

export async function processTorrentMetadata(jobId: string) {
  const job = await db.torrentProcessingJob.findUnique({ where: { id: jobId } });
  if (!job) {
    throw new NotFoundError("Torrent processing job was not found.");
  }

  const torrent = await db.torrent.findUnique({ where: { id: job.torrentId } });
  if (!torrent) {
    throw new NotFoundError("Torrent was not found.");
  }

  const provider = buildTorrentProvider();
  const blobStore = buildBlobStore();

  try {
    const metadata = await provider.fetch(torrent.infoHash);
    const blobKey = `torrents/${torrent.infoHash}.torrent`;
    await blobStore.putBytes(blobKey, metadata.raw);

    await db.$transaction(async (tx) => {
      await tx.torrentFile.deleteMany({ where: { torrentId: torrent.id } });
      await tx.torrent.update({
        where: { id: torrent.id },
        data: {
          name: metadata.name,
          sizeBytes: BigInt(metadata.sizeBytes),
          rawBlobKey: blobKey,
          metadataStatus: "succeeded",
          metadataError: null,
        },
      });
      if (metadata.files.length > 0) {
        await tx.torrentFile.createMany({
          data: metadata.files.map((file, index) => ({
            torrentId: torrent.id,
            path: file.path,
            sizeBytes: BigInt(file.sizeBytes),
            position: index,
          })),
        });
      }
      await tx.torrentProcessingJob.update({
        where: { id: job.id },
        data: {
          status: "succeeded",
          finishedAt: new Date(),
          leaseExpiresAt: null,
          lastHeartbeatAt: new Date(),
        },
      });
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to process torrent metadata.";
    await db.$transaction(async (tx) => {
      await tx.torrent.update({
        where: { id: torrent.id },
        data: {
          metadataStatus: "failed",
          metadataError: message,
        },
      });
      await tx.torrentProcessingJob.update({
        where: { id: job.id },
        data: {
          status: "failed",
          error: message,
          finishedAt: new Date(),
          leaseExpiresAt: null,
          lastHeartbeatAt: new Date(),
        },
      });
    });
  }
}

function toVideoSummary(video: VideoRecord): VideoSummary {
  return {
    id: video.id,
    displayTitle: video.title ?? video.torrent.name,
    title: video.title,
    rating: video.rating,
    infoHash: video.torrent.infoHash,
    torrentName: video.torrent.name,
    metadataStatus: video.torrent.metadataStatus as VideoSummary["metadataStatus"],
    tags: toTags(video),
    createdAt: video.createdAt.toISOString(),
    updatedAt: video.updatedAt.toISOString(),
  };
}

function toVideoDetail(video: VideoRecord): VideoDetail {
  return {
    ...toVideoSummary(video),
    description: video.description,
    sizeBytes: video.torrent.sizeBytes === null ? null : Number(video.torrent.sizeBytes),
    metadataError: video.torrent.metadataError,
    files: video.torrent.files.map<TorrentFileRead>((file) => ({
      path: file.path,
      sizeBytes: Number(file.sizeBytes),
    })),
  };
}

function toTags(video: VideoRecord): TagRead[] {
  return video.videoTags.map((videoTag) => ({
    id: videoTag.tag.id,
    name: videoTag.tag.name,
  }));
}
