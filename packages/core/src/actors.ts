import { randomUUID } from "node:crypto";
import {
  ActorModel,
  connectMongo,
  TorrentModel,
  type ActorDoc,
} from "./db.js";
import { ConflictError, NotFoundError } from "./errors.js";
import { buildBlobStore } from "./storage.js";
import type { ActorRead } from "./types.js";

export type ActorImageInput = {
  bytes: Uint8Array;
  mimeType: string;
};

const supportedActorImageTypes = new Map([
  ["image/jpeg", "jpg"],
  ["image/png", "png"],
  ["image/webp", "webp"],
  ["image/gif", "gif"],
]);

const maxActorImageBytes = 5 * 1024 * 1024;

export async function listActors() {
  await connectMongo();
  const actors = await ActorModel.find().lean().exec();
  return actors.sort(compareActorNames).map(toActorRead);
}

export async function getActorById(actorId: string) {
  await connectMongo();
  const actor = await ActorModel.findById(actorId).lean().exec();
  if (!actor) {
    throw new NotFoundError("Actor was not found.");
  }
  return toActorRead(actor);
}

export async function getActorProfileImage(actorId: string) {
  await connectMongo();
  const actor = await ActorModel.findById(actorId).lean().exec();
  if (!actor) {
    throw new NotFoundError("Actor was not found.");
  }

  const bytes = await buildBlobStore().getBytes(actor.profileImageKey);
  return {
    bytes,
    key: actor.profileImageKey,
    mimeType: actor.profileImageMimeType,
  };
}

export async function createActor(input: {
  name: string;
  description: string | null;
  image: ActorImageInput;
}) {
  await connectMongo();
  const normalizedName = normalizeActorName(input.name);
  const existing = await ActorModel.findOne({ name: normalizedName }).lean().exec();
  if (existing) {
    throw new ConflictError("Actor name already exists.");
  }

  validateActorImage(input.image);
  const actorId = randomUUID();
  const key = actorImageKey(actorId, input.image.mimeType);
  await buildBlobStore().putBytes(key, input.image.bytes);
  try {
    const created = await ActorModel.create({
      _id: actorId,
      name: normalizedName,
      description: normalizeActorDescription(input.description),
      profileImageKey: key,
      profileImageMimeType: input.image.mimeType,
    });
    return toActorRead(created.toObject() as ActorDoc);
  } catch (error) {
    await buildBlobStore().deleteIfExists(key);
    if (isDuplicateKeyError(error)) {
      throw new ConflictError("Actor name already exists.");
    }
    throw error;
  }
}

export async function updateActor(
  actorId: string,
  input: {
    name: string;
    description: string | null;
    image?: ActorImageInput | null;
  },
) {
  await connectMongo();
  const actor = await ActorModel.findById(actorId).lean().exec();
  if (!actor) {
    throw new NotFoundError("Actor was not found.");
  }

  const normalizedName = normalizeActorName(input.name);
  const existing = await ActorModel.findOne({ name: normalizedName }).lean().exec();
  if (existing && existing._id !== actorId) {
    throw new ConflictError("Actor name already exists.");
  }

  const update: Partial<Pick<ActorDoc, "name" | "description" | "profileImageKey" | "profileImageMimeType">> = {
    name: normalizedName,
    description: normalizeActorDescription(input.description),
  };
  let oldImageKey: string | null = null;
  let newImageKey: string | null = null;
  if (input.image) {
    validateActorImage(input.image);
    update.profileImageKey = actorImageKey(actor._id, input.image.mimeType);
    update.profileImageMimeType = input.image.mimeType;
    oldImageKey = actor.profileImageKey;
    newImageKey = update.profileImageKey;
    await buildBlobStore().putBytes(update.profileImageKey, input.image.bytes);
  }

  let updated: ActorDoc | null;
  try {
    updated = await ActorModel.findByIdAndUpdate(actorId, { $set: update }, { new: true }).lean().exec();
  } catch (error) {
    if (newImageKey) {
      await buildBlobStore().deleteIfExists(newImageKey);
    }
    if (isDuplicateKeyError(error)) {
      throw new ConflictError("Actor name already exists.");
    }
    throw error;
  }
  if (!updated) {
    if (newImageKey) {
      await buildBlobStore().deleteIfExists(newImageKey);
    }
    throw new NotFoundError("Actor was not found.");
  }
  if (oldImageKey && oldImageKey !== update.profileImageKey) {
    await buildBlobStore().deleteIfExists(oldImageKey);
  }
  return toActorRead(updated);
}

export async function deleteActor(actorId: string) {
  await connectMongo();
  const actor = await ActorModel.findById(actorId).lean().exec();
  if (!actor) {
    throw new NotFoundError("Actor was not found.");
  }

  await Promise.all([
    ActorModel.deleteOne({ _id: actorId }).exec(),
    TorrentModel.updateMany({}, { $pull: { actorIds: actorId } }).exec(),
  ]);
  await buildBlobStore().deleteIfExists(actor.profileImageKey);
}

export async function resolveActorIds(actorIds: string[]) {
  await connectMongo();
  const uniqueActorIds = [...new Set(actorIds.map((actorId) => actorId.trim()).filter(Boolean))];
  if (uniqueActorIds.length === 0) {
    return [];
  }

  const actors = await ActorModel.find({ _id: { $in: uniqueActorIds } }).select({ _id: 1 }).lean().exec();
  if (actors.length !== uniqueActorIds.length) {
    throw new NotFoundError("One or more actors were not found.");
  }

  return uniqueActorIds;
}

function toActorRead(actor: ActorDoc): ActorRead {
  return {
    id: actor._id,
    name: actor.name,
    description: actor.description,
    hasProfileImage: Boolean(actor.profileImageKey),
    createdAt: actor.createdAt.toISOString(),
    updatedAt: actor.updatedAt.toISOString(),
  };
}

function normalizeActorName(name: string) {
  const normalized = name.trim().replace(/\s+/g, " ");
  if (!normalized) {
    throw new ConflictError("Actor name is required.");
  }
  return normalized;
}

function normalizeActorDescription(description: string | null | undefined) {
  if (!description) {
    return null;
  }
  const normalized = description.trim();
  return normalized ? normalized : null;
}

function validateActorImage(image: ActorImageInput) {
  if (!supportedActorImageTypes.has(image.mimeType)) {
    throw new ConflictError("Profile image must be a JPEG, PNG, WebP, or GIF file.");
  }
  if (image.bytes.byteLength === 0) {
    throw new ConflictError("Profile image is required.");
  }
  if (image.bytes.byteLength > maxActorImageBytes) {
    throw new ConflictError("Profile image must be 5 MB or smaller.");
  }
}

function actorImageKey(actorId: string, mimeType: string) {
  const extension = supportedActorImageTypes.get(mimeType) ?? "img";
  return `actors/${actorId}/profile-${randomUUID()}.${extension}`;
}

function compareActorNames(a: ActorDoc, b: ActorDoc) {
  return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
}

function isDuplicateKeyError(error: unknown) {
  return typeof error === "object" && error !== null && "code" in error && error.code === 11000;
}
