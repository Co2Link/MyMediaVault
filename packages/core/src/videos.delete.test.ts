import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const state = {
    torrents: [] as Array<Record<string, unknown>>,
    videos: [] as Array<Record<string, unknown>>,
    aggregate: [] as Array<{ _id: string; videoCount: number }>,
    videoCount: 0,
    videoFindOne: null as Record<string, unknown> | null,
    torrentFindById: null as Record<string, unknown> | null,
  };

  const blobStore = {
    deleteIfExists: vi.fn(),
  };

  const connectMongo = vi.fn();

  const query = <T>(value: T) => ({
    lean: () => ({
      exec: vi.fn(async () => value),
    }),
    exec: vi.fn(async () => value),
  });

  const models = {
    TagModel: {},
    TorrentModel: {
      find: vi.fn(() => query(state.torrents)),
      findById: vi.fn(() => query(state.torrentFindById)),
      deleteOne: vi.fn(() => query({ deletedCount: 1 })),
    },
    VideoModel: {
      find: vi.fn(() => query(state.videos)),
      findOne: vi.fn(() => query(state.videoFindOne)),
      deleteOne: vi.fn(() => query({ deletedCount: 1 })),
      deleteMany: vi.fn(() => query({ deletedCount: 1 })),
      countDocuments: vi.fn(() => query(state.videoCount)),
      aggregate: vi.fn(() => ({
        exec: vi.fn(async () => state.aggregate),
      })),
    },
    VideoTagModel: {
      deleteMany: vi.fn(() => query({ deletedCount: 1 })),
    },
    TorrentMetadataJobModel: {
      deleteMany: vi.fn(() => query({ deletedCount: 1 })),
    },
  };

  return { blobStore, connectMongo, models, state };
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
  buildBlobStore: () => mocks.blobStore,
}));

vi.mock("./torrent-provider.js", () => ({
  buildTorrentProvider: vi.fn(),
}));

vi.mock("./env.js", () => ({
  getTorrentEnv: vi.fn(() => ({})),
}));

describe("torrent and video deletion", () => {
  beforeEach(() => {
    mocks.connectMongo.mockClear();
    mocks.blobStore.deleteIfExists.mockClear();
    for (const model of Object.values(mocks.models)) {
      for (const fn of Object.values(model as Record<string, unknown>)) {
        if (typeof fn === "function" && "mockReset" in fn) {
          (fn as { mockClear: () => void }).mockClear();
        }
      }
    }
    mocks.state.torrents = [];
    mocks.state.videos = [];
    mocks.state.aggregate = [];
    mocks.state.videoCount = 0;
    mocks.state.videoFindOne = null;
    mocks.state.torrentFindById = null;
  });

  it("lists torrents with descending recency and video counts", async () => {
    mocks.state.torrents = [
      {
        _id: "torrent-old",
        infoHash: "old",
        name: "Old Torrent",
        sizeBytes: 10,
        rawBlobKey: "torrents/old.torrent",
        metadataStatus: "succeeded",
        metadataError: null,
        metadataAttempts: 1,
        metadataLastAttemptAt: null,
        files: [],
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-01T00:00:00Z"),
      },
      {
        _id: "torrent-new",
        infoHash: "new",
        name: "New Torrent",
        sizeBytes: 20,
        rawBlobKey: "torrents/new.torrent",
        metadataStatus: "pending",
        metadataError: null,
        metadataAttempts: 0,
        metadataLastAttemptAt: null,
        files: [],
        createdAt: new Date("2024-02-01T00:00:00Z"),
        updatedAt: new Date("2024-02-01T00:00:00Z"),
      },
    ];
    mocks.state.aggregate = [
      { _id: "torrent-old", videoCount: 1 },
      { _id: "torrent-new", videoCount: 3 },
    ];

    const { listTorrents } = await import("./videos.js");
    await expect(listTorrents()).resolves.toEqual([
      expect.objectContaining({ id: "torrent-new", videoCount: 3 }),
      expect.objectContaining({ id: "torrent-old", videoCount: 1 }),
    ]);
  });

  it("deletes a user's video and removes the orphan torrent blob", async () => {
    mocks.state.videoFindOne = {
      _id: "video-1",
      userId: "user-1",
      torrentId: "torrent-1",
      title: "Video",
      description: null,
      rating: null,
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    mocks.state.videoCount = 0;
    mocks.state.torrentFindById = {
      _id: "torrent-1",
      infoHash: "abc",
      name: "Torrent",
      sizeBytes: 123,
      rawBlobKey: "torrents/abc.torrent",
      metadataStatus: "succeeded",
      metadataError: null,
      metadataAttempts: 1,
      metadataLastAttemptAt: null,
      files: [],
      previewFrames: [
        { key: "previews/abc/frame-1.jpg" },
        { key: "previews/abc/frame-2.jpg" },
      ],
      previewSheet: { key: "previews/abc/sheet.jpg" },
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    const { deleteVideo } = await import("./videos.js");
    await deleteVideo("user-1", "video-1");

    expect(mocks.models.VideoTagModel.deleteMany).toHaveBeenCalledWith({ videoId: "video-1" });
    expect(mocks.models.VideoModel.deleteOne).toHaveBeenCalledWith({ _id: "video-1", userId: "user-1" });
    expect(mocks.models.TorrentMetadataJobModel.deleteMany).toHaveBeenCalledWith({ torrentId: "torrent-1" });
    expect(mocks.models.TorrentModel.deleteOne).toHaveBeenCalledWith({ _id: "torrent-1" });
    expect(mocks.blobStore.deleteIfExists).toHaveBeenCalledWith("torrents/abc.torrent");
    expect(mocks.blobStore.deleteIfExists).toHaveBeenCalledWith("previews/abc/frame-1.jpg");
    expect(mocks.blobStore.deleteIfExists).toHaveBeenCalledWith("previews/abc/frame-2.jpg");
    expect(mocks.blobStore.deleteIfExists).toHaveBeenCalledWith("previews/abc/sheet.jpg");
  });

  it("deletes an admin-managed torrent together with its videos and blob", async () => {
    mocks.state.torrentFindById = {
      _id: "torrent-2",
      infoHash: "def",
      name: "Torrent",
      sizeBytes: 123,
      rawBlobKey: "torrents/def.torrent",
      metadataStatus: "succeeded",
      metadataError: null,
      metadataAttempts: 1,
      metadataLastAttemptAt: null,
      files: [],
      previewFrames: [{ key: "previews/def/frame-1.jpg" }],
      previewSheet: { key: "previews/def/sheet.jpg" },
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    mocks.state.videos = [
      {
        _id: "video-a",
        torrentId: "torrent-2",
        userId: "user-a",
        title: null,
        description: null,
        rating: null,
        createdAt: new Date(),
        updatedAt: new Date(),
      },
      {
        _id: "video-b",
        torrentId: "torrent-2",
        userId: "user-b",
        title: null,
        description: null,
        rating: null,
        createdAt: new Date(),
        updatedAt: new Date(),
      },
    ];

    const { deleteTorrent } = await import("./videos.js");
    await deleteTorrent("torrent-2");

    expect(mocks.models.VideoTagModel.deleteMany).toHaveBeenCalledWith({
      videoId: { $in: ["video-a", "video-b"] },
    });
    expect(mocks.models.VideoModel.deleteMany).toHaveBeenCalledWith({
      _id: { $in: ["video-a", "video-b"] },
    });
    expect(mocks.models.TorrentMetadataJobModel.deleteMany).toHaveBeenCalledWith({ torrentId: "torrent-2" });
    expect(mocks.models.TorrentModel.deleteOne).toHaveBeenCalledWith({ _id: "torrent-2" });
    expect(mocks.blobStore.deleteIfExists).toHaveBeenCalledWith("torrents/def.torrent");
    expect(mocks.blobStore.deleteIfExists).toHaveBeenCalledWith("previews/def/frame-1.jpg");
    expect(mocks.blobStore.deleteIfExists).toHaveBeenCalledWith("previews/def/sheet.jpg");
  });
});
