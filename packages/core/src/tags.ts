import { connectMongo, TagModel } from "./db.js";
import { ConflictError, NotFoundError } from "./errors.js";
import type { TagRead } from "./types.js";

export async function listTags() {
  await connectMongo();
  const tags = await TagModel.find().lean().exec();
  return tags
    .sort((a, b) => a.name.localeCompare(b.name))
    .map<TagRead>((tag) => ({
      id: tag._id,
      name: tag.name,
    }));
}

export async function createTag(name: string) {
  await connectMongo();
  const normalized = normalizeName(name);
  const existing = await TagModel.findOne({ name: normalized }).lean().exec();
  if (existing) {
    throw new ConflictError("Tag name already exists.");
  }
  return TagModel.create({ name: normalized });
}

export async function updateTag(id: string, name: string) {
  await connectMongo();
  const normalized = normalizeName(name);
  const tag = await TagModel.findById(id).lean().exec();
  if (!tag) {
    throw new NotFoundError("Tag was not found.");
  }
  const existing = await TagModel.findOne({ name: normalized }).lean().exec();
  if (existing && existing._id !== id) {
    throw new ConflictError("Tag name already exists.");
  }
  return TagModel.findByIdAndUpdate(id, { $set: { name: normalized } }, { new: true }).lean().exec();
}

export async function deleteTag(id: string) {
  await connectMongo();
  const result = await TagModel.deleteOne({ _id: id }).exec();
  if (result.deletedCount === 0) {
    throw new NotFoundError("Tag was not found.");
  }
}

function normalizeName(name: string) {
  const normalized = name.trim().replace(/\s+/g, " ");
  if (!normalized) {
    throw new ConflictError("Tag name is required.");
  }
  return normalized;
}
