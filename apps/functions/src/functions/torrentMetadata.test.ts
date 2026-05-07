import { describe, expect, it } from "vitest";

describe("torrent metadata functions", () => {
  it("uses the default torrent metadata queue name", async () => {
    const previous = process.env.MMV_TORRENT_METADATA_QUEUE;
    delete process.env.MMV_TORRENT_METADATA_QUEUE;
    await import("./torrentMetadata.js");
    expect(process.env.MMV_TORRENT_METADATA_QUEUE).toBeUndefined();
    if (previous === undefined) {
      delete process.env.MMV_TORRENT_METADATA_QUEUE;
    } else {
      process.env.MMV_TORRENT_METADATA_QUEUE = previous;
    }
  });
});
