import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const connectMongo = vi.fn();
  const state = {
    torrent: {
      _id: "torrent-1",
      infoHash: "abc",
      processingState: "exhausted",
      processingLastError: "old error",
      rawBlobKey: null,
    } as Record<string, unknown> | null,
  };

  const query = <T>(value: T) => ({
    lean: () => ({
      exec: vi.fn(async () => value),
    }),
    exec: vi.fn(async () => value),
  });

  const models = {
    ActorModel: {},
    TagModel: {},
    TorrentModel: {
      findById: vi.fn(() => query(state.torrent)),
      updateOne: vi.fn(() => query({ acknowledged: true })),
    },
    VideoModel: {},
    VideoTagModel: {},
  };

  return { connectMongo, models, state };
});

vi.mock("./db.js", () => ({
  connectMongo: mocks.connectMongo,
  ActorModel: mocks.models.ActorModel,
  TagModel: mocks.models.TagModel,
  TorrentModel: mocks.models.TorrentModel,
  VideoModel: mocks.models.VideoModel,
  VideoTagModel: mocks.models.VideoTagModel,
}));

vi.mock("./storage.js", () => ({
  buildBlobStore: () => ({ putBytes: vi.fn(), deleteIfExists: vi.fn() }),
}));

describe("torrent processing scheduling", () => {
  beforeEach(() => {
    mocks.connectMongo.mockClear();
    mocks.models.TorrentModel.findById.mockClear();
    mocks.models.TorrentModel.updateOne.mockClear();
    mocks.state.torrent = {
      _id: "torrent-1",
      infoHash: "abc",
      processingState: "exhausted",
      processingLastError: "old error",
      rawBlobKey: null,
    };
  });

  it("queues torrent processing for the VM worker", async () => {
    const { queueTorrentProcessing } = await import("./videos.js");

    await expect(queueTorrentProcessing("torrent-1")).resolves.toEqual({ torrentId: "torrent-1" });

    expect(mocks.models.TorrentModel.updateOne).toHaveBeenCalledWith(
      { _id: "torrent-1" },
      {
        $set: {
          processingState: "queued",
          processingPhase: null,
          processingQueuedAt: expect.any(Date),
          processingAvailableAt: null,
          processingLeaseUntil: null,
          processingFailureCount: 0,
          processingLastOutcome: "queued_by_admin",
          processingLastError: null,
          processingUpdatedAt: expect.any(Date),
        },
      },
    );
  });

  it("allows an admin to queue completed torrent processing again", async () => {
    mocks.state.torrent = {
      _id: "torrent-1",
      infoHash: "abc",
      processingState: "complete",
      processingLastError: null,
      rawBlobKey: "torrents/abc.torrent",
    };
    const { queueTorrentProcessing } = await import("./videos.js");

    await expect(queueTorrentProcessing("torrent-1")).resolves.toEqual({ torrentId: "torrent-1" });

    expect(mocks.models.TorrentModel.updateOne).toHaveBeenCalledOnce();
  });
});
