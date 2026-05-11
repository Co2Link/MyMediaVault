import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const connectMongo = vi.fn();
  const jobState = {
    claimedJob: {
      _id: "job-1",
      torrentId: "torrent-1",
      status: "processing",
      attempt: 1,
      error: null,
      lastDequeuedAt: null,
      startedAt: null,
      finishedAt: null,
      createdAt: new Date("2024-01-01T00:00:00Z"),
      updatedAt: new Date("2024-01-01T00:00:00Z"),
    },
    staleJob: {
      _id: "job-2",
      torrentId: "torrent-2",
      status: "processing",
      attempt: 1,
      error: "stuck",
      lastDequeuedAt: new Date("2024-01-01T00:00:00Z"),
      startedAt: new Date("2024-01-01T00:00:00Z"),
      finishedAt: null,
      createdAt: new Date("2024-01-01T00:00:00Z"),
      updatedAt: new Date("2024-01-01T00:00:00Z"),
    },
  };

  const query = <T>(value: T) => ({
    lean: () => ({
      exec: vi.fn(async () => value),
    }),
    exec: vi.fn(async () => value),
  });

  const models = {
    TagModel: {},
    TorrentModel: {},
    VideoModel: {},
    VideoTagModel: {},
    TorrentMetadataJobModel: {
      findOneAndUpdate: vi.fn(() => query(jobState.claimedJob)),
      find: vi.fn(() => query([jobState.staleJob])),
      updateOne: vi.fn(() => query({ acknowledged: true })),
    },
  };

  return { connectMongo, models, jobState };
});

vi.mock("./db.js", () => ({
  connectMongo: mocks.connectMongo,
  TagModel: mocks.models.TagModel,
  TorrentModel: mocks.models.TorrentModel,
  VideoModel: mocks.models.VideoModel,
  VideoTagModel: mocks.models.VideoTagModel,
  TorrentMetadataJobModel: mocks.models.TorrentMetadataJobModel,
}));

vi.mock("./storage.js", () => ({
  buildBlobStore: () => ({ putBytes: vi.fn(), deleteIfExists: vi.fn() }),
}));

vi.mock("./torrent-provider.js", () => ({
  buildTorrentProvider: vi.fn(),
}));

vi.mock("./env.js", () => ({
  getEnv: vi.fn(() => ({
    torrentRepairStaleProcessingMinutes: 30,
  })),
}));

describe("torrent metadata scheduling", () => {
  beforeEach(() => {
    mocks.connectMongo.mockClear();
    for (const model of Object.values(mocks.models)) {
      for (const fn of Object.values(model as Record<string, unknown>)) {
        if (typeof fn === "function" && "mockClear" in fn) {
          (fn as { mockClear: () => void }).mockClear();
        }
      }
    }
  });

  it("claims the oldest queued torrent metadata job", async () => {
    const { claimNextTorrentMetadataJob } = await import("./videos.js");

    await expect(claimNextTorrentMetadataJob()).resolves.toMatchObject({
      _id: "job-1",
      status: "processing",
    });
    expect(mocks.models.TorrentMetadataJobModel.findOneAndUpdate).toHaveBeenCalledWith(
      { status: "queued" },
      {
        $set: {
          status: "processing",
          error: null,
          lastDequeuedAt: expect.any(Date),
        },
      },
      {
        new: true,
        sort: { createdAt: 1, _id: 1 },
      },
    );
  });

  it("requeues stale processing jobs", async () => {
    const { repairStaleTorrentMetadataJobs } = await import("./videos.js");

    await expect(repairStaleTorrentMetadataJobs(new Date("2024-01-02T00:00:00Z"))).resolves.toEqual({ repaired: 1 });
    expect(mocks.models.TorrentMetadataJobModel.find).toHaveBeenCalledWith({
      $or: [
        {
          status: "processing",
          $or: [{ lastDequeuedAt: null }, { lastDequeuedAt: { $lt: expect.any(Date) } }],
        },
      ],
    });
    expect(mocks.models.TorrentMetadataJobModel.updateOne).toHaveBeenCalledWith(
      { _id: "job-2" },
      { $set: { status: "queued", error: null } },
    );
  });
});
