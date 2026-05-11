function getRequiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export function getEnv() {
  return {
    authSecret: getRequiredEnv("AUTH_SECRET"),
    authClientId: getRequiredEnv("AUTH_MICROSOFT_ENTRA_ID_ID"),
    authClientSecret: getRequiredEnv("AUTH_MICROSOFT_ENTRA_ID_SECRET"),
    authIssuer: getRequiredEnv("AUTH_MICROSOFT_ENTRA_ID_ISSUER"),
    mongodbUri: getRequiredEnv("MONGODB_URI"),
    mongodbDatabase: process.env.MMV_MONGODB_DB_NAME ?? "mymediavault",
    mongodbServerSelectionTimeoutMs: Number(process.env.MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS ?? "10000"),
    commitSha: process.env.MMV_COMMIT_SHA ?? "local",
    adminObjectIds: parseJsonArray("MMV_ADMIN_OBJECT_IDS"),
    adminGroupObjectIds: parseJsonArray("MMV_ADMIN_GROUP_OBJECT_IDS"),
    r2Endpoint: process.env.R2_ENDPOINT,
    r2AccessKeyId: process.env.R2_ACCESS_KEY_ID,
    r2SecretAccessKey: process.env.R2_SECRET_ACCESS_KEY,
    r2BucketName: process.env.R2_BUCKET_NAME ?? "torrent-raw",
    torrentProvider: process.env.MMV_TORRENT_PROVIDER ?? "fake",
    torrentResolverUrls: parseJsonArray("MMV_TORRENT_RESOLVER_URLS"),
    torrentFetchTimeoutSeconds: Number(process.env.MMV_TORRENT_FETCH_TIMEOUT_SECONDS ?? "20"),
    torrentRepairStaleQueuedMinutes: Number(process.env.MMV_TORRENT_REPAIR_STALE_QUEUED_MINUTES ?? "10"),
    torrentRepairStaleProcessingMinutes: Number(process.env.MMV_TORRENT_REPAIR_STALE_PROCESSING_MINUTES ?? "30"),
  };
}

function parseJsonArray(name: string, fallback: string[] = []) {
  const value = process.env[name];
  if (!value) {
    return fallback;
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    if (Array.isArray(parsed) && parsed.every((item) => typeof item === "string")) {
      return parsed;
    }
  } catch {
    // Fall through to delimited parsing.
  }
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
