import "../load-env";
import { BlobServiceClient } from "@azure/storage-blob";
import { rm } from "node:fs/promises";
import path from "node:path";
import { db } from "../src/lib/db";
import { getEnv } from "../src/lib/env";

async function main() {
  const usernames = [process.env.E2E_USER_USERNAME, process.env.E2E_ADMIN_USERNAME].filter(
    (value): value is string => Boolean(value),
  );
  if (usernames.length === 0) {
    throw new Error("Missing required environment variables: E2E_USER_USERNAME and E2E_ADMIN_USERNAME");
  }
  const displayNames = usernames.map((username) => username.split("@")[0] ?? username);

  const targetUsers = await db.user.findMany({
    where: {
      OR: [
        { email: { in: usernames } },
        ...displayNames.map((displayName) => ({
          name: displayName,
          accounts: {
            some: {
              provider: "microsoft-entra-id",
            },
          },
        })),
      ],
    },
    include: {
      videos: {
        select: {
          torrentId: true,
        },
      },
    },
  });

  const candidateTorrentIds = new Set(targetUsers.flatMap((user) => user.videos.map((video) => video.torrentId)));

  await db.tag.deleteMany({
    where: {
      name: {
        startsWith: "e2e-tag-",
      },
    },
  });

  if (targetUsers.length > 0) {
    await db.user.deleteMany({
      where: {
        id: {
          in: targetUsers.map((user) => user.id),
        },
      },
    });
  }

  if (candidateTorrentIds.size === 0) {
    return;
  }

  const orphanedTorrents = await db.torrent.findMany({
    where: {
      id: {
        in: [...candidateTorrentIds],
      },
      videos: {
        none: {},
      },
    },
    select: {
      id: true,
      rawBlobKey: true,
    },
  });

  if (orphanedTorrents.length === 0) {
    return;
  }

  await deleteRawBlobs(orphanedTorrents.map((torrent) => torrent.rawBlobKey).filter((key): key is string => Boolean(key)));

  await db.torrent.deleteMany({
    where: {
      id: {
        in: orphanedTorrents.map((torrent) => torrent.id),
      },
    },
  });
}

async function deleteRawBlobs(keys: string[]) {
  if (keys.length === 0) {
    return;
  }

  const env = getEnv();
  if (env.azureStorageConnectionString) {
    const container = BlobServiceClient.fromConnectionString(env.azureStorageConnectionString).getContainerClient(
      env.azureBlobContainer,
    );
    await Promise.all(keys.map((key) => container.deleteBlob(key).catch(() => undefined)));
    return;
  }

  const root = path.join(process.cwd(), ".local", "blob-storage");
  await Promise.all(keys.map((key) => rm(path.join(root, key), { force: true })));
}

void main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await db.$disconnect();
  });
