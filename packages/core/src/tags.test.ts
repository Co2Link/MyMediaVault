import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const connectMongo = vi.fn();
  const query = <T>(value: T) => ({
    lean: () => ({
      exec: vi.fn(async () => value),
    }),
    exec: vi.fn(async () => value),
  });
  const models = {
    TagModel: {
      findById: vi.fn((id: string) => query(id === "tag-1" ? { _id: "tag-1", name: "Drama" } : null)),
      deleteOne: vi.fn(() => query({ deletedCount: 1 })),
    },
    VideoTagModel: {
      deleteMany: vi.fn(() => query({ deletedCount: 1 })),
    },
  };

  return { connectMongo, models };
});

vi.mock("./db.js", () => ({
  connectMongo: mocks.connectMongo,
  TagModel: mocks.models.TagModel,
  VideoTagModel: mocks.models.VideoTagModel,
}));

describe("tag deletion", () => {
  beforeEach(() => {
    mocks.connectMongo.mockClear();
    mocks.models.TagModel.findById.mockClear();
    mocks.models.TagModel.deleteOne.mockClear();
    mocks.models.VideoTagModel.deleteMany.mockClear();
  });

  it("deletes video tag links after deleting the tag", async () => {
    const { deleteTag } = await import("./tags.js");

    await expect(deleteTag("tag-1")).resolves.toBeUndefined();

    expect(mocks.models.TagModel.deleteOne).toHaveBeenCalledWith({ _id: "tag-1" });
    expect(mocks.models.VideoTagModel.deleteMany).toHaveBeenCalledWith({ tagId: "tag-1" });
  });

  it("returns a tag by id", async () => {
    const { getTagById } = await import("./tags.js");

    await expect(getTagById("tag-1")).resolves.toEqual({ id: "tag-1", name: "Drama" });
  });

  it("rejects an unknown tag id", async () => {
    const { getTagById } = await import("./tags.js");

    await expect(getTagById("missing-tag")).rejects.toMatchObject({ statusCode: 404 });
  });
});
