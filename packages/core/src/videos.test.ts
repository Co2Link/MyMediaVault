import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const connectMongo = vi.fn();
  const state = {
    torrent: {
      _id: "torrent-1",
      infoHash: "abc",
      metadataStatus: "failed",
      metadataError: "old error",
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

describe("torrent metadata scheduling", () => {
  beforeEach(() => {
    mocks.connectMongo.mockClear();
    mocks.models.TorrentModel.findById.mockClear();
    mocks.models.TorrentModel.updateOne.mockClear();
    mocks.state.torrent = {
      _id: "torrent-1",
      infoHash: "abc",
      metadataStatus: "failed",
      metadataError: "old error",
      rawBlobKey: null,
    };
  });

  it("marks unfinished torrent metadata ready for the VM worker", async () => {
    const { enqueueTorrentMetadata } = await import("./videos.js");

    await expect(enqueueTorrentMetadata("torrent-1")).resolves.toEqual({ torrentId: "torrent-1" });

    expect(mocks.models.TorrentModel.updateOne).toHaveBeenCalledWith(
      { _id: "torrent-1" },
      {
        $set: {
          metadataStatus: "pending",
          metadataError: null,
          metadataFailureKind: null,
          metadataNextAttemptAt: null,
          metadataLeaseUntil: null,
          metadataFinishedAt: null,
        },
      },
    );
  });

  it("does not requeue completed torrent metadata", async () => {
    mocks.state.torrent = {
      _id: "torrent-1",
      infoHash: "abc",
      metadataStatus: "succeeded",
      metadataError: null,
      rawBlobKey: "torrents/abc.torrent",
    };
    const { enqueueTorrentMetadata } = await import("./videos.js");

    await expect(enqueueTorrentMetadata("torrent-1")).resolves.toBeNull();

    expect(mocks.models.TorrentModel.updateOne).not.toHaveBeenCalled();
  });
});
