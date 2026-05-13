import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const connectMongo = vi.fn();
  const query = <T>(value: T) => ({
    exec: vi.fn(async () => value),
  });
  const models = {
    TagModel: {
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
    mocks.models.TagModel.deleteOne.mockClear();
    mocks.models.VideoTagModel.deleteMany.mockClear();
  });

  it("deletes video tag links after deleting the tag", async () => {
    const { deleteTag } = await import("./tags.js");

    await expect(deleteTag("tag-1")).resolves.toBeUndefined();

    expect(mocks.models.TagModel.deleteOne).toHaveBeenCalledWith({ _id: "tag-1" });
    expect(mocks.models.VideoTagModel.deleteMany).toHaveBeenCalledWith({ tagId: "tag-1" });
  });
});
