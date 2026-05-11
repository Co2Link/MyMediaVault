import { getEnv } from "@mymediavault/core/env";
import { processPendingTorrentMetadataJobs, repairStaleTorrentMetadataJobs } from "@mymediavault/core/videos";

const env = getEnv();

console.log("Scheduled torrent metadata worker started", {
  r2Endpoint: env.r2Endpoint ? new URL(env.r2Endpoint).host : null,
});

const repaired = await repairStaleTorrentMetadataJobs();
if (repaired.repaired > 0) {
  console.log("Torrent metadata jobs repaired", repaired);
}

const result = await processPendingTorrentMetadataJobs(10);
console.log("Scheduled torrent metadata worker finished", result);
