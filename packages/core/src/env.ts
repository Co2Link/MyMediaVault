function getRequiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export function getEnv() {
  return {
    ...getAuthEnv(),
    ...getDatabaseEnv(),
    ...getAppEnv(),
    ...getStorageEnv(),
  };
}

export function getAuthEnv() {
  return {
    authSecret: getRequiredEnv("AUTH_SECRET"),
    authClientId: getRequiredEnv("AUTH_MICROSOFT_ENTRA_ID_ID"),
    authClientSecret: getRequiredEnv("AUTH_MICROSOFT_ENTRA_ID_SECRET"),
    authIssuer: getRequiredEnv("AUTH_MICROSOFT_ENTRA_ID_ISSUER"),
    adminObjectIds: parseJsonArray("MMV_ADMIN_OBJECT_IDS"),
    adminGroupObjectIds: parseJsonArray("MMV_ADMIN_GROUP_OBJECT_IDS"),
  };
}

export function getDatabaseEnv() {
  return {
    mongodbUri: getRequiredEnv("MONGODB_URI"),
    mongodbDatabase: process.env.MMV_MONGODB_DB_NAME ?? "mymediavault",
    mongodbServerSelectionTimeoutMs: Number(process.env.MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS ?? "10000"),
  };
}

export function getAppEnv() {
  return {
    commitSha: process.env.MMV_COMMIT_SHA ?? "local",
  };
}

export function getStorageEnv() {
  return {
    r2Endpoint: process.env.R2_ENDPOINT,
    r2AccessKeyId: process.env.R2_ACCESS_KEY_ID,
    r2SecretAccessKey: process.env.R2_SECRET_ACCESS_KEY,
    r2BucketName: process.env.R2_BUCKET_NAME ?? "torrent-raw",
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
