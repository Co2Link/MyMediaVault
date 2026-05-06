import "../../load-env";
import { randomUUID } from "node:crypto";
import { getEnv } from "@/lib/env";
import { claimTorrentProcessingJob, heartbeatTorrentProcessingJob, processTorrentMetadata } from "@/lib/videos";

const env = getEnv();
const workerId = `worker-${randomUUID()}`;

async function run() {
  for (;;) {
    const job = await claimTorrentProcessingJob(workerId, env.torrentJobLeaseSeconds);
    if (!job) {
      await sleep(env.torrentWorkerPollIntervalSeconds * 1000);
      continue;
    }

    await heartbeatTorrentProcessingJob(job.id, env.torrentJobLeaseSeconds);
    await processTorrentMetadata(job.id);
  }
}

void run().catch((error) => {
  console.error(error);
  process.exit(1);
});

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
