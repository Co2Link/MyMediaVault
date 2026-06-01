import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const state = {
    tags: [
      { _id: "tag-1", name: "Drama" },
      { _id: "tag-2", name: "Favorites" },
    ] as Array<Record<string, unknown>>,
    actors: [
      {
        _id: "actor-1",
        name: "Actor One",
        description: "First actor",
        profileImageKey: "actors/actor-1/profile.jpg",
        profileImageMimeType: "image/jpeg",
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-01T00:00:00Z"),
      },
      {
        _id: "actor-2",
        name: "Actor Two",
        description: null,
        profileImageKey: "actors/actor-2/profile.jpg",
        profileImageMimeType: "image/jpeg",
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-01T00:00:00Z"),
      },
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
    ActorModel: {
      find: vi.fn((filter?: { _id?: { $in?: string[] } }) => {
        const ids = filter?._id?.$in;
        const value = ids ? state.actors.filter((actor) => ids.includes(actor._id as string)) : state.actors;
        return query(value);
      }),
    },
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
          userActorIds: Array.isArray(doc.userActorIds) ? doc.userActorIds : [],
          createdAt: new Date("2024-01-01T00:00:00Z"),
          updatedAt: new Date("2024-01-01T00:00:00Z"),
          toObject() {
            return this;
          },
        };
        state.torrents.push(created);
        return created;
      }),
      updateOne: vi.fn((filter: { _id?: string }, update: { $set?: Record<string, unknown>; $unset?: Record<string, unknown> }) => {
        const torrent = state.torrents.find((entry) => entry._id === filter._id);
        if (torrent && update.$set) {
          Object.assign(torrent, update.$set);
        }
        if (torrent && update.$unset) {
          for (const key of Object.keys(update.$unset)) {
            delete torrent[key];
          }
        }
        return query({ acknowledged: true });
      }),
    },
    VideoModel: {
      find: vi.fn((filter?: { userId?: string }) =>
        query(state.videos.filter((video) => !filter?.userId || video.userId === filter.userId)),
      ),
      findOne: vi.fn((filter?: { _id?: string; userId?: string; torrentId?: string }) =>
        query(
          state.videos.find(
            (video) =>
              (!filter?._id || video._id === filter._id) &&
              (!filter?.userId || video.userId === filter.userId) &&
              (!filter?.torrentId || video.torrentId === filter.torrentId),
          ) ?? null,
        ),
      ),
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
      actorIds: [],
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
        actorIds: [],
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
      actorIds: [],
    });

    expect(mocks.models.VideoTagModel.deleteMany).toHaveBeenCalledWith({ videoId: "video-1" });
    expect(mocks.models.VideoTagModel.create).toHaveBeenCalledWith([{ videoId: "video-1", tagId: "tag-2" }]);
    expect(video.tags.map((tag) => tag.id)).toEqual(["tag-2"]);
  });

  it("stores selected actors on the shared torrent when creating a video", async () => {
    const { createVideo } = await import("./videos.js");

    const video = await createVideo("user-1", {
      infoHash: "abcdef0123456789abcdef0123456789abcdef01",
      title: "Title",
      description: null,
      rating: null,
      tagIds: [],
      actorIds: ["actor-2", "actor-1", "actor-2"],
    });

    expect(mocks.state.torrents[0]?.userActorIds).toEqual(["actor-2", "actor-1"]);
    expect(video.actors.map((actor) => actor.id)).toEqual(["actor-1", "actor-2"]);
  });

  it("replaces torrent actors when updating video details", async () => {
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
        actorIds: ["actor-1"],
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-01T00:00:00Z"),
      },
    ];

    const { updateVideo } = await import("./videos.js");

    const video = await updateVideo("user-1", "video-1", {
      title: "Updated title",
      description: null,
      rating: null,
      tagIds: [],
      actorIds: ["actor-2"],
    });

    expect(mocks.models.TorrentModel.updateOne).toHaveBeenCalledWith(
      { _id: "torrent-1" },
      { $set: { userActorIds: ["actor-2"] }, $unset: { actorIds: "" } },
    );
    expect(video.actors.map((actor) => actor.id)).toEqual(["actor-2"]);
  });

  it("deduplicates system and user actors while preserving provenance", async () => {
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
        systemActorIds: ["actor-1", "actor-2"],
        userActorIds: ["actor-2"],
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-01T00:00:00Z"),
      },
    ];
    mocks.state.videos = [
      {
        _id: "video-1",
        userId: "user-1",
        torrentId: "torrent-1",
        title: null,
        description: null,
        rating: null,
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-01T00:00:00Z"),
      },
    ];

    const { getVideoById } = await import("./videos.js");

    const video = await getVideoById("user-1", "video-1");

    expect(video.actors.map((actor) => actor.id)).toEqual(["actor-1", "actor-2"]);
    expect(video.systemActors.map((actor) => actor.id)).toEqual(["actor-1", "actor-2"]);
    expect(video.userActors.map((actor) => actor.id)).toEqual(["actor-2"]);
  });

  it("lists the user's newest videos for both detected and manually assigned actors", async () => {
    mocks.state.torrents = [
      makeTorrent("torrent-1", { systemActorIds: ["actor-1"] }),
      makeTorrent("torrent-2", { userActorIds: ["actor-1"] }),
      makeTorrent("torrent-3", { userActorIds: ["actor-2"] }),
    ];
    mocks.state.videos = [
      makeVideo("video-1", "user-1", "torrent-1", "2024-01-01T00:00:00Z"),
      makeVideo("video-2", "user-1", "torrent-2", "2024-01-03T00:00:00Z"),
      makeVideo("video-3", "user-2", "torrent-1", "2024-01-04T00:00:00Z"),
      makeVideo("video-4", "user-1", "torrent-3", "2024-01-02T00:00:00Z"),
    ];

    const { listVideosByActor } = await import("./videos.js");

    const videos = await listVideosByActor("user-1", "actor-1");

    expect(videos.map((video) => video.id)).toEqual(["video-2", "video-1"]);
  });

  it("lists only the user's newest videos with a selected tag", async () => {
    mocks.state.torrents = [
      makeTorrent("torrent-1"),
      makeTorrent("torrent-2"),
      makeTorrent("torrent-3"),
    ];
    mocks.state.videos = [
      makeVideo("video-1", "user-1", "torrent-1", "2024-01-01T00:00:00Z"),
      makeVideo("video-2", "user-1", "torrent-2", "2024-01-03T00:00:00Z"),
      makeVideo("video-3", "user-2", "torrent-3", "2024-01-04T00:00:00Z"),
    ];
    mocks.state.videoTags = [
      { _id: "video-tag-1", videoId: "video-1", tagId: "tag-1", createdAt: new Date("2024-01-01T00:00:00Z") },
      { _id: "video-tag-2", videoId: "video-2", tagId: "tag-1", createdAt: new Date("2024-01-01T00:00:00Z") },
      { _id: "video-tag-3", videoId: "video-3", tagId: "tag-1", createdAt: new Date("2024-01-01T00:00:00Z") },
    ];

    const { listVideosByTag } = await import("./videos.js");

    const videos = await listVideosByTag("user-1", "tag-1");

    expect(videos.map((video) => video.id)).toEqual(["video-2", "video-1"]);
  });

  it("returns empty lists when the user's collection has no matching actor or tag", async () => {
    mocks.state.torrents = [makeTorrent("torrent-1", { userActorIds: ["actor-1"] })];
    mocks.state.videos = [makeVideo("video-1", "user-1", "torrent-1", "2024-01-01T00:00:00Z")];
    mocks.state.videoTags = [
      { _id: "video-tag-1", videoId: "video-1", tagId: "tag-1", createdAt: new Date("2024-01-01T00:00:00Z") },
    ];

    const { listVideosByActor, listVideosByTag } = await import("./videos.js");

    await expect(listVideosByActor("user-1", "actor-2")).resolves.toEqual([]);
    await expect(listVideosByTag("user-1", "tag-2")).resolves.toEqual([]);
  });
});

function makeTorrent(id: string, actors: { systemActorIds?: string[]; userActorIds?: string[] } = {}) {
  return {
    _id: id,
    infoHash: `${id}-hash`,
    name: id,
    sizeBytes: 123,
    rawBlobKey: null,
    metadataStatus: "succeeded",
    metadataError: null,
    metadataAttempts: 1,
    metadataLastAttemptAt: null,
    files: [],
    systemActorIds: actors.systemActorIds ?? [],
    userActorIds: actors.userActorIds ?? [],
    createdAt: new Date("2024-01-01T00:00:00Z"),
    updatedAt: new Date("2024-01-01T00:00:00Z"),
  };
}

function makeVideo(id: string, userId: string, torrentId: string, createdAt: string) {
  return {
    _id: id,
    userId,
    torrentId,
    title: id,
    description: null,
    rating: null,
    createdAt: new Date(createdAt),
    updatedAt: new Date(createdAt),
  };
}
