import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  processPendingTorrentMetadataJobs: vi.fn(),
  repairStaleTorrentMetadataJobs: vi.fn(),
}));

vi.mock("@mymediavault/core/videos", () => ({
  processPendingTorrentMetadataJobs: mocks.processPendingTorrentMetadataJobs,
  repairStaleTorrentMetadataJobs: mocks.repairStaleTorrentMetadataJobs,
}));

describe("torrent metadata worker drain", () => {
  beforeEach(() => {
    mocks.processPendingTorrentMetadataJobs.mockReset();
    mocks.repairStaleTorrentMetadataJobs.mockReset();
    mocks.repairStaleTorrentMetadataJobs.mockResolvedValue({ repaired: 0 });
    mocks.processPendingTorrentMetadataJobs.mockResolvedValue({ processed: 0 });
  });

  it("drains full batches until the queue is empty", async () => {
    const logger = { log: vi.fn() };
    mocks.repairStaleTorrentMetadataJobs.mockResolvedValueOnce({ repaired: 1 });
    mocks.processPendingTorrentMetadataJobs
      .mockResolvedValueOnce({ processed: 10 })
      .mockResolvedValueOnce({ processed: 2 });
    const { drainTorrentMetadataJobs } = await import("./torrentMetadataWorker.js");

    await expect(drainTorrentMetadataJobs(10, logger)).resolves.toEqual({
      repaired: 1,
      processed: 12,
      batches: 2,
    });

    expect(mocks.processPendingTorrentMetadataJobs).toHaveBeenCalledTimes(2);
    expect(logger.log).toHaveBeenCalledWith("Torrent metadata jobs repaired", { repaired: 1 });
  });

  it("exits without processing when no queued jobs are available", async () => {
    const { drainTorrentMetadataJobs } = await import("./torrentMetadataWorker.js");

    await expect(drainTorrentMetadataJobs()).resolves.toEqual({
      repaired: 0,
      processed: 0,
      batches: 0,
    });

    expect(mocks.processPendingTorrentMetadataJobs).toHaveBeenCalledWith(10);
  });
});
