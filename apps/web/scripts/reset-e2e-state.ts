import "../load-env";
import { resetE2EState, db } from "@mymediavault/core/db";
import { buildBlobStore } from "@mymediavault/core/storage";

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

  const blobStore = buildBlobStore();
  await Promise.all(keys.map((key) => blobStore.deleteIfExists(key)));
}

void main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await db.disconnect();
  });
