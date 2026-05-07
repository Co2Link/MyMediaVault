import "../load-env";
import { BlobServiceClient } from "@azure/storage-blob";
import { resetE2EState, db } from "@mymediavault/core/db";
import { rm } from "node:fs/promises";
import path from "node:path";
import { getEnv } from "../src/lib/env";

async function main() {
  const usernames = [process.env.E2E_USER_USERNAME, process.env.E2E_ADMIN_USERNAME].filter(
    (value): value is string => Boolean(value),
  );
  if (usernames.length === 0) {
    throw new Error("Missing required environment variables: E2E_USER_USERNAME and E2E_ADMIN_USERNAME");
  }

  const { rawBlobKeys } = await resetE2EState(usernames);
  await deleteRawBlobs(rawBlobKeys);
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
    await db.disconnect();
  });
