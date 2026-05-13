import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const state = {
    tags: [
      { _id: "tag-1", name: "Drama" },
      { _id: "tag-2", name: "Favorites" },
    ] as Array<Record<string, unknown>>,
    torrents: [] as Array<Record<string, unknown>>,
    videos: [] as Array<Record<string, unknown>>,
    videoTags: [] as Array<Record<string, unknown>>,
  };

  const connectMongo = vi.fn();

  const query = <T>(value: T) => ({
    select: () => ({
      lean: () => ({
        exec: vi.fn(async () => value),
      }),
    }),
    lean: () => ({
      exec: vi.fn(async () => value),
    }),
    exec: vi.fn(async () => value),
  });

  const models = {
    TagModel: {
      find: vi.fn((filter?: { _id?: { $in?: string[] } }) => {
        const ids = filter?._id?.$in;
        const value = ids ? state.tags.filter((tag) => ids.includes(tag._id as string)) : state.tags;
        return query(value);
      }),
    },
    TorrentModel: {
      findOne: vi.fn(() => query(state.torrents[0] ?? null)),
      findById: vi.fn((id: string) => query(state.torrents.find((torrent) => torrent._id === id) ?? null)),
      find: vi.fn((filter?: { _id?: { $in?: string[] } }) => {
        const ids = filter?._id?.$in;
        const value = ids ? state.torrents.filter((torrent) => ids.includes(torrent._id as string)) : state.torrents;
        return query(value);
      }),
      create: vi.fn(async (doc: Record<string, unknown>) => {
        const created = {
          _id: `torrent-${state.torrents.length + 1}`,
          ...doc,
          name: null,
          sizeBytes: null,
          rawBlobKey: null,
          metadataStatus: "pending",
          metadataError: null,
          metadataAttempts: 0,
          metadataLastAttemptAt: null,
          files: [],
          createdAt: new Date("2024-01-01T00:00:00Z"),
          updatedAt: new Date("2024-01-01T00:00:00Z"),
          toObject() {
            return this;
          },
        };
        state.torrents.push(created);
        return created;
      }),
      updateOne: vi.fn(() => query({ acknowledged: true })),
    },
    VideoModel: {
      findOne: vi.fn(() => query(null)),
      findOneAndUpdate: vi.fn((_filter: Record<string, unknown>, update: { $set: Record<string, unknown> }) =>
        query({
          _id: "video-1",
          userId: "user-1",
          torrentId: "torrent-1",
          title: update.$set.title ?? null,
          description: update.$set.description ?? null,
          rating: update.$set.rating ?? null,
          createdAt: new Date("2024-01-01T00:00:00Z"),
          updatedAt: new Date("2024-01-02T00:00:00Z"),
        }),
      ),
      create: vi.fn(async (doc: Record<string, unknown>) => {
        const created = {
          _id: "video-1",
          ...doc,
          createdAt: new Date("2024-01-01T00:00:00Z"),
          updatedAt: new Date("2024-01-01T00:00:00Z"),
          toObject() {
            return this;
          },
        };
        state.videos.push(created);
        return created;
      }),
      deleteOne: vi.fn(() => query({ deletedCount: 1 })),
      deleteMany: vi.fn(() => query({ deletedCount: 1 })),
      countDocuments: vi.fn(() => query(0)),
      aggregate: vi.fn(() => ({
        exec: vi.fn(async () => []),
      })),
    },
    VideoTagModel: {
      find: vi.fn((filter?: { videoId?: { $in?: string[] } }) => {
        const ids = filter?.videoId?.$in;
        const value = ids ? state.videoTags.filter((videoTag) => ids.includes(videoTag.videoId as string)) : state.videoTags;
        return query(value);
      }),
      deleteMany: vi.fn((filter: { videoId?: string | { $in?: string[] } }) => {
        if (typeof filter.videoId === "string") {
          state.videoTags = state.videoTags.filter((videoTag) => videoTag.videoId !== filter.videoId);
        } else if (filter.videoId?.$in) {
          state.videoTags = state.videoTags.filter((videoTag) => !filter.videoId?.$in?.includes(videoTag.videoId as string));
        }
        return query({ deletedCount: 1 });
      }),
      create: vi.fn(async (docs: Array<Record<string, unknown>>) => {
        for (const doc of docs) {
          state.videoTags.push({
            _id: `video-tag-${state.videoTags.length + 1}`,
            createdAt: new Date("2024-01-01T00:00:00Z"),
            ...doc,
          });
        }
        return docs;
      }),
    },
    TorrentMetadataJobModel: {
      find: vi.fn(() => query([])),
      create: vi.fn(async (doc: Record<string, unknown>) => ({
        _id: "job-1",
        ...doc,
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-01T00:00:00Z"),
        toObject() {
          return this;
        },
      })),
      updateOne: vi.fn(() => query({ acknowledged: true })),
      findById: vi.fn(() => query(null)),
    },
  };

  return { connectMongo, models, state };
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
  getTorrentEnv: vi.fn(() => ({})),
}));

describe("video tag persistence", () => {
  beforeEach(() => {
    mocks.connectMongo.mockClear();
    for (const model of Object.values(mocks.models)) {
      for (const fn of Object.values(model as Record<string, unknown>)) {
        if (typeof fn === "function" && "mockClear" in fn) {
          (fn as { mockClear: () => void }).mockClear();
        }
      }
    }
    mocks.state.torrents = [];
    mocks.state.videos = [];
    mocks.state.videoTags = [];
  });

  it("persists selected tags when creating a video", async () => {
    const { createVideo } = await import("./videos.js");

    const video = await createVideo("user-1", {
      infoHash: "abcdef0123456789abcdef0123456789abcdef01",
      title: "Title",
      description: "Description",
      rating: 4,
      tagIds: ["tag-2", "tag-1", "tag-2"],
    });

    expect(mocks.models.VideoTagModel.deleteMany).toHaveBeenCalledWith({ videoId: "video-1" });
    expect(mocks.models.VideoTagModel.create).toHaveBeenCalledWith([
      { videoId: "video-1", tagId: "tag-2" },
      { videoId: "video-1", tagId: "tag-1" },
    ]);
    expect(video.tags.map((tag) => tag.id)).toEqual(["tag-1", "tag-2"]);
  });

  it("replaces existing tags when updating a video", async () => {
    mocks.state.torrents = [
      {
        _id: "torrent-1",
        infoHash: "abcdef0123456789abcdef0123456789abcdef01",
        name: "Torrent",
        sizeBytes: 123,
        rawBlobKey: null,
        metadataStatus: "succeeded",
        metadataError: null,
        metadataAttempts: 1,
        metadataLastAttemptAt: null,
        files: [],
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-01T00:00:00Z"),
      },
    ];
    mocks.state.videoTags = [
      { _id: "video-tag-1", videoId: "video-1", tagId: "tag-1", createdAt: new Date("2024-01-01T00:00:00Z") },
    ];

    const { updateVideo } = await import("./videos.js");

    const video = await updateVideo("user-1", "video-1", {
      title: "Updated title",
      description: null,
      rating: null,
      tagIds: ["tag-2"],
    });

    expect(mocks.models.VideoTagModel.deleteMany).toHaveBeenCalledWith({ videoId: "video-1" });
    expect(mocks.models.VideoTagModel.create).toHaveBeenCalledWith([{ videoId: "video-1", tagId: "tag-2" }]);
    expect(video.tags.map((tag) => tag.id)).toEqual(["tag-2"]);
  });
});
