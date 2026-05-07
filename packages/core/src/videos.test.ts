import { describe, expect, it } from "vitest";

describe("parseTorrentMetadataQueueMessage", () => {
  it("accepts versioned job messages", async () => {
    const { parseTorrentMetadataQueueMessage } = await import("./videos.js");
    expect(parseTorrentMetadataQueueMessage(JSON.stringify({ version: 1, jobId: "job-1" }))).toEqual({
      version: 1,
      jobId: "job-1",
    });
  });

  it("rejects invalid messages", async () => {
    const { parseTorrentMetadataQueueMessage } = await import("./videos.js");
    expect(() => parseTorrentMetadataQueueMessage(JSON.stringify({ version: 2, jobId: "job-1" }))).toThrow(
      "Invalid torrent metadata queue message.",
    );
  });
});
