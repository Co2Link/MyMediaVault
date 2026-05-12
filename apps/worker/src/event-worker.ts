import { getEnv } from "@mymediavault/core/env";
import { drainTorrentMetadataJobs } from "./torrentMetadataWorker.js";

const env = getEnv();

console.log("Event torrent metadata worker started", {
  r2Endpoint: env.r2Endpoint ? new URL(env.r2Endpoint).host : null,
});

const result = await drainTorrentMetadataJobs();
console.log("Event torrent metadata worker finished", result);
