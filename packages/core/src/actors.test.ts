import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const connectMongo = vi.fn();
  const blobStore = {
    putBytes: vi.fn(async (key: string) => key),
    getBytes: vi.fn(async () => new Uint8Array([1, 2, 3])),
    deleteIfExists: vi.fn(),
  };
  const state = {
    actors: [
      {
        _id: "actor-1",
        name: "Jane Actor",
        description: "Performer",
        profileImageKey: "actors/actor-1/profile.jpg",
        profileImageMimeType: "image/jpeg",
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-02T00:00:00Z"),
      },
    ] as Array<Record<string, unknown>>,
  };

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
      find: vi.fn(() => query(state.actors)),
      findOne: vi.fn((filter: { name?: string }) =>
        query(state.actors.find((actor) => actor.name === filter.name) ?? null),
      ),
      findById: vi.fn((id: string) => query(state.actors.find((actor) => actor._id === id) ?? null)),
      findByIdAndUpdate: vi.fn((id: string, update: { $set: Record<string, unknown> }) => {
        const actor = state.actors.find((entry) => entry._id === id);
        if (!actor) {
          return query(null);
        }
        Object.assign(actor, update.$set, { updatedAt: new Date("2024-01-03T00:00:00Z") });
        return query(actor);
      }),
      create: vi.fn(async (doc: Record<string, unknown>) => {
        const created = {
          ...doc,
          createdAt: new Date("2024-02-01T00:00:00Z"),
          updatedAt: new Date("2024-02-01T00:00:00Z"),
          toObject() {
            return this;
          },
        };
        state.actors.push(created);
        return created;
      }),
      deleteOne: vi.fn(() => query({ deletedCount: 1 })),
    },
    TorrentModel: {
      updateMany: vi.fn(() => query({ modifiedCount: 1 })),
    },
  };

  return { blobStore, connectMongo, models, state };
});

vi.mock("./db.js", () => ({
  connectMongo: mocks.connectMongo,
  ActorModel: mocks.models.ActorModel,
  TorrentModel: mocks.models.TorrentModel,
}));

vi.mock("./storage.js", () => ({
  buildBlobStore: () => mocks.blobStore,
}));

describe("actors", () => {
  beforeEach(() => {
    mocks.connectMongo.mockClear();
    mocks.blobStore.putBytes.mockClear();
    mocks.blobStore.getBytes.mockClear();
    mocks.blobStore.deleteIfExists.mockClear();
    for (const model of Object.values(mocks.models)) {
      for (const fn of Object.values(model as Record<string, unknown>)) {
        if (typeof fn === "function" && "mockClear" in fn) {
          (fn as { mockClear: () => void }).mockClear();
        }
      }
    }
    mocks.state.actors = [
      {
        _id: "actor-1",
        name: "Jane Actor",
        description: "Performer",
        profileImageKey: "actors/actor-1/profile.jpg",
        profileImageMimeType: "image/jpeg",
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-02T00:00:00Z"),
      },
    ];
  });

  it("creates an actor and stores the profile image", async () => {
    const { createActor } = await import("./actors.js");

    const actor = await createActor({
      name: "  New   Actor  ",
      description: "  Description  ",
      image: { bytes: new Uint8Array([1, 2, 3]), mimeType: "image/png" },
    });

    expect(actor.name).toBe("New Actor");
    expect(actor.description).toBe("Description");
    expect(actor.hasProfileImage).toBe(true);
    expect(mocks.blobStore.putBytes).toHaveBeenCalledWith(expect.stringMatching(/^actors\/.+\/profile-.+\.png$/), new Uint8Array([1, 2, 3]));
    expect(mocks.models.ActorModel.create).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "New Actor",
        description: "Description",
        profileImageMimeType: "image/png",
        profileImageSource: "admin",
      }),
    );
  });

  it("returns an actor by id", async () => {
    const { getActorById } = await import("./actors.js");

    await expect(getActorById("actor-1")).resolves.toMatchObject({ id: "actor-1", name: "Jane Actor" });
  });

  it("rejects an unknown actor id", async () => {
    const { getActorById } = await import("./actors.js");

    await expect(getActorById("missing-actor")).rejects.toMatchObject({ statusCode: 404 });
  });

  it("updates actor details and replaces the profile image", async () => {
    const { updateActor } = await import("./actors.js");

    const actor = await updateActor("actor-1", {
      name: "Jane Updated",
      description: null,
      image: { bytes: new Uint8Array([4]), mimeType: "image/webp" },
    });

    expect(actor.name).toBe("Jane Updated");
    expect(actor.description).toBeNull();
    expect(mocks.blobStore.putBytes).toHaveBeenCalledWith(expect.stringMatching(/^actors\/actor-1\/profile-.+\.webp$/), new Uint8Array([4]));
    expect(mocks.blobStore.deleteIfExists).toHaveBeenCalledWith("actors/actor-1/profile.jpg");
    expect(mocks.models.ActorModel.findByIdAndUpdate).toHaveBeenCalledWith(
      "actor-1",
      expect.objectContaining({
        $set: expect.objectContaining({ profileImageSource: "admin" }),
        $unset: {
          profileImageVersion: "",
          profileImageScore: "",
          profileImageFlags: "",
          profileImageSourceTorrentId: "",
          profileImageSourceFrameKey: "",
          profileImageUpdatedAt: "",
        },
      }),
      { new: true },
    );
  });

  it("deletes actor references and the profile image", async () => {
    const { deleteActor } = await import("./actors.js");

    await deleteActor("actor-1");

    expect(mocks.models.ActorModel.deleteOne).toHaveBeenCalledWith({ _id: "actor-1" });
    expect(mocks.models.TorrentModel.updateMany).toHaveBeenCalledWith(
      {},
      {
        $pull: {
          actorIds: "actor-1",
          userActorIds: "actor-1",
          systemActorIds: "actor-1",
        },
      },
    );
    expect(mocks.blobStore.deleteIfExists).toHaveBeenCalledWith("actors/actor-1/profile.jpg");
  });
});
