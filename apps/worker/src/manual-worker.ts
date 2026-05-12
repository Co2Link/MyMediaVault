import { getEnv } from "@mymediavault/core/env";
import { processPendingTorrentMetadataJobs, repairStaleTorrentMetadataJobs } from "@mymediavault/core/videos";

const env = getEnv();

let shuttingDown = false;
const sleep = (milliseconds: number) => new Promise<void>((resolve) => setTimeout(resolve, milliseconds));

process.on("SIGINT", () => {
  shuttingDown = true;
});

process.on("SIGTERM", () => {
  shuttingDown = true;
});

console.log("Manual torrent metadata worker started", {
  r2Endpoint: env.r2Endpoint ? new URL(env.r2Endpoint).host : null,
});

while (!shuttingDown) {
  const repaired = await repairStaleTorrentMetadataJobs();
  if (repaired.repaired > 0) {
    console.log("Torrent metadata jobs repaired", repaired);
  }

  const result = await processPendingTorrentMetadataJobs(10);
  if (result.processed === 0) {
    await sleep(1000);
    continue;
  }
}
