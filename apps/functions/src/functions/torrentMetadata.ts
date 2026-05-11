import { app, type InvocationContext, type Timer } from "@azure/functions";
import { processPendingTorrentMetadataJobs, repairStaleTorrentMetadataJobs } from "@mymediavault/core/videos";

app.timer("processTorrentMetadata", {
  schedule: "0 * * * * *",
  handler: async (_timer: Timer, context: InvocationContext) => {
    const repaired = await repairStaleTorrentMetadataJobs();
    if (repaired.repaired > 0) {
      context.log("Torrent metadata jobs repaired", repaired);
    }

    const result = await processPendingTorrentMetadataJobs(10);
    context.log("Torrent metadata timer run finished", {
      ...result,
      invocationId: context.invocationId,
    });
  },
});
