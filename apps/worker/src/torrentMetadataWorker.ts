import { processPendingTorrentMetadataJobs, repairStaleTorrentMetadataJobs } from "@mymediavault/core/videos";

type WorkerLogger = Pick<typeof console, "log">;

export type TorrentMetadataWorkerResult = {
  repaired: number;
  processed: number;
  batches: number;
};

export async function drainTorrentMetadataJobs(
  batchSize = 10,
  logger: WorkerLogger = console,
): Promise<TorrentMetadataWorkerResult> {
  const effectiveBatchSize = Math.max(1, Math.floor(batchSize));
  const repaired = await repairStaleTorrentMetadataJobs();
  if (repaired.repaired > 0) {
    logger.log("Torrent metadata jobs repaired", repaired);
  }

  let processed = 0;
  let batches = 0;

  while (true) {
    const result = await processPendingTorrentMetadataJobs(effectiveBatchSize);
    if (result.processed === 0) {
      break;
    }

    processed += result.processed;
    batches += 1;

    if (result.processed < effectiveBatchSize) {
      break;
    }
  }

  return {
    repaired: repaired.repaired,
    processed,
    batches,
  };
}
