import { QueueClient, type ReceivedMessageItem } from "@azure/storage-queue";
import { getEnv } from "@mymediavault/core/env";
import { parseTorrentMetadataQueueMessage, processTorrentMetadataJob } from "@mymediavault/core/videos";

const env = getEnv();
const connectionString = env.azureStorageConnectionString ?? env.azureWebJobsStorage;

if (!connectionString) {
  throw new Error("Missing Azure storage connection string for manual worker.");
}

const queueClient = new QueueClient(connectionString, env.torrentMetadataQueue);
await queueClient.createIfNotExists();

let shuttingDown = false;
const sleep = (milliseconds: number) => new Promise<void>((resolve) => setTimeout(resolve, milliseconds));

process.on("SIGINT", () => {
  shuttingDown = true;
});

process.on("SIGTERM", () => {
  shuttingDown = true;
});

console.log("Manual torrent metadata worker started", {
  queueName: env.torrentMetadataQueue,
});

while (!shuttingDown) {
  const { receivedMessageItems } = await queueClient.receiveMessages({
    numberOfMessages: 1,
    visibilityTimeout: 30,
  });
  const message = receivedMessageItems[0];

  if (!message) {
    await sleep(1000);
    continue;
  }

  await handleMessage(message);
}

async function handleMessage(message: ReceivedMessageItem) {
  const payload = parseTorrentMetadataQueueMessage(message.messageText);
  console.log("Processing torrent metadata job", { jobId: payload.jobId });
  const result = await processTorrentMetadataJob(payload.jobId);
  await queueClient.deleteMessage(message.messageId, message.popReceipt);
  console.log("Torrent metadata job completed", result);
}
