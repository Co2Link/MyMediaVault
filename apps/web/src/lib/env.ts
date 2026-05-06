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
    commitSha: process.env.MMV_COMMIT_SHA ?? "local",
    adminObjectIds: parseJsonArray("MMV_ADMIN_OBJECT_IDS"),
    adminGroupObjectIds: parseJsonArray("MMV_ADMIN_GROUP_OBJECT_IDS"),
    azureStorageConnectionString: process.env.MMV_AZURE_STORAGE_CONNECTION_STRING,
    azureBlobContainer: process.env.MMV_AZURE_BLOB_CONTAINER ?? "torrent-raw",
    torrentProvider: process.env.MMV_TORRENT_PROVIDER ?? "fake",
    torrentResolverUrls: parseJsonArray("MMV_TORRENT_RESOLVER_URLS"),
    torrentFetchTimeoutSeconds: Number(process.env.MMV_TORRENT_FETCH_TIMEOUT_SECONDS ?? "20"),
    torrentWorkerPollIntervalSeconds: Number(process.env.MMV_TORRENT_WORKER_POLL_INTERVAL_SECONDS ?? "2"),
    torrentJobLeaseSeconds: Number(process.env.MMV_TORRENT_JOB_LEASE_SECONDS ?? "30"),
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
