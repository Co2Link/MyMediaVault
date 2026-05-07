import { app, type InvocationContext, type Timer } from "@azure/functions";
import {
  markTorrentMetadataPoisoned,
  parseTorrentMetadataQueueMessage,
  processTorrentMetadataJob,
  repairStaleTorrentMetadataJobs,
} from "@mymediavault/core/videos";

const queueName = process.env.MMV_TORRENT_METADATA_QUEUE ?? "torrent-metadata-jobs";

app.storageQueue("processTorrentMetadata", {
  queueName,
  connection: "AzureWebJobsStorage",
  handler: async (message: unknown, context: InvocationContext) => {
    const parsed = parseTorrentMetadataQueueMessage(message);
    context.log("Processing torrent metadata job", { jobId: parsed.jobId, invocationId: context.invocationId });
    const result = await processTorrentMetadataJob(parsed.jobId);
    context.log("Torrent metadata job completed", result);
  },
});

app.storageQueue("markTorrentMetadataPoisoned", {
  queueName: `${queueName}-poison`,
  connection: "AzureWebJobsStorage",
  handler: async (message: unknown, context: InvocationContext) => {
    const result = await markTorrentMetadataPoisoned(message);
    context.warn("Torrent metadata job moved to poison queue", result);
  },
});

app.timer("repairTorrentMetadataQueue", {
  schedule: "0 */5 * * * *",
  handler: async (_timer: Timer, context: InvocationContext) => {
    const result = await repairStaleTorrentMetadataJobs();
    context.log("Torrent metadata queue repair finished", result);
  },
});
