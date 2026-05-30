import { randomUUID } from "node:crypto";
import mongoose, { Schema, type Model } from "mongoose";
import { getDatabaseEnv } from "./env.js";
import type { MetadataFailureKind, MetadataStatus, PreviewStatus } from "./types.js";

export type UserDoc = {
  _id: string;
  name: string | null;
  email: string | null;
  emailVerified: Date | null;
  image: string | null;
  entraOid: string | null;
  isAdmin: boolean;
  createdAt: Date;
  updatedAt: Date;
};

export type AccountDoc = {
  _id: string;
  userId: string;
  type: string;
  provider: string;
  providerAccountId: string;
  refresh_token?: string | null;
  access_token?: string | null;
  expires_at?: number | null;
  token_type?: string | null;
  scope?: string | null;
  id_token?: string | null;
  session_state?: string | null;
  refresh_token_expires_in?: number | null;
  createdAt: Date;
  updatedAt: Date;
};

export type SessionDoc = {
  _id: string;
  sessionToken: string;
  userId: string;
  expires: Date;
};

export type VerificationTokenDoc = {
  _id: string;
  identifier: string;
  token: string;
  expires: Date;
};

export type TagDoc = {
  _id: string;
  name: string;
  createdAt: Date;
  updatedAt: Date;
};

export type ActorDoc = {
  _id: string;
  name: string;
  description: string | null;
  profileImageKey: string;
  profileImageMimeType: string;
  createdAt: Date;
  updatedAt: Date;
};

export type TorrentFileDoc = {
  path: string;
  sizeBytes: number;
  position: number;
};

export type TorrentPreviewFrameDoc = {
  key: string;
  width: number;
  height: number;
  timestampSeconds: number;
};

export type TorrentPreviewSheetDoc = {
  key: string;
  width: number;
  height: number;
  mimeType: string;
};

export type TorrentPreviewDiagnosticsDoc = {
  artifactVersion: string | null;
  artifactFingerprint: string | null;
  statusReason: string | null;
  downloadedBytes: number | null;
  elapsedSeconds: number | null;
  selectedFilePath: string | null;
  selectedFileSizeBytes: number | null;
  warnings: string[];
  details: Record<string, unknown>;
};

export type TorrentDoc = {
  _id: string;
  infoHash: string;
  name: string | null;
  sizeBytes: number | null;
  rawBlobKey: string | null;
  metadataStatus: MetadataStatus;
  metadataError: string | null;
  metadataFailureKind: MetadataFailureKind | null;
  metadataAttempts: number;
  metadataNextAttemptAt: Date | null;
  metadataLastAttemptAt: Date | null;
  metadataStartedAt: Date | null;
  metadataFinishedAt: Date | null;
  metadataLeaseUntil: Date | null;
  metadataDiagnostics: Record<string, unknown>;
  files: TorrentFileDoc[];
  actorIds: string[];
  previewStatus: PreviewStatus;
  previewAttempts: number;
  previewLastAttemptAt: Date | null;
  previewNextAttemptAt: Date | null;
  previewUpdatedAt: Date | null;
  previewFrames: TorrentPreviewFrameDoc[];
  previewSheet: TorrentPreviewSheetDoc | null;
  previewDiagnostics: TorrentPreviewDiagnosticsDoc;
  createdAt: Date;
  updatedAt: Date;
};

export type VideoDoc = {
  _id: string;
  userId: string;
  torrentId: string;
  title: string | null;
  description: string | null;
  rating: number | null;
  createdAt: Date;
  updatedAt: Date;
};

export type VideoTagDoc = {
  _id: string;
  videoId: string;
  tagId: string;
  createdAt: Date;
};

type GlobalMongoose = {
  mongooseConnection?: Promise<typeof mongoose>;
  mongooseInstance?: typeof mongoose;
};

const globalForMongoose = globalThis as unknown as GlobalMongoose;

const schemaOptions = {
  versionKey: false,
  timestamps: true,
} as const;

const userSchema = new Schema<UserDoc>(
  {
    _id: { type: String, default: newId },
    name: { type: String, default: null },
    email: { type: String, default: null },
    emailVerified: { type: Date, default: null },
    image: { type: String, default: null },
    entraOid: { type: String, default: null },
    isAdmin: { type: Boolean, default: false },
  },
  schemaOptions,
);
userSchema.index({ email: 1 }, { unique: true, sparse: true });
userSchema.index({ entraOid: 1 }, { unique: true, sparse: true });

const accountSchema = new Schema<AccountDoc>(
  {
    _id: { type: String, default: newId },
    userId: { type: String, required: true, index: true },
    type: { type: String, required: true },
    provider: { type: String, required: true },
    providerAccountId: { type: String, required: true },
    refresh_token: { type: String, default: null },
    access_token: { type: String, default: null },
    expires_at: { type: Number, default: null },
    token_type: { type: String, default: null },
    scope: { type: String, default: null },
    id_token: { type: String, default: null },
    session_state: { type: String, default: null },
    refresh_token_expires_in: { type: Number, default: null },
  },
  schemaOptions,
);
accountSchema.index({ provider: 1, providerAccountId: 1 }, { unique: true });
accountSchema.index({ userId: 1, provider: 1 });

const sessionSchema = new Schema<SessionDoc>(
  {
    _id: { type: String, default: newId },
    sessionToken: { type: String, required: true, unique: true },
    userId: { type: String, required: true, index: true },
    expires: { type: Date, required: true },
  },
  { versionKey: false },
);

const verificationTokenSchema = new Schema<VerificationTokenDoc>(
  {
    _id: { type: String, default: newId },
    identifier: { type: String, required: true },
    token: { type: String, required: true },
    expires: { type: Date, required: true },
  },
  { versionKey: false },
);
verificationTokenSchema.index({ identifier: 1, token: 1 }, { unique: true });

const tagSchema = new Schema<TagDoc>(
  {
    _id: { type: String, default: newId },
    name: { type: String, required: true, unique: true },
  },
  schemaOptions,
);

const actorSchema = new Schema<ActorDoc>(
  {
    _id: { type: String, default: newId },
    name: { type: String, required: true, unique: true },
    description: { type: String, default: null },
    profileImageKey: { type: String, required: true },
    profileImageMimeType: { type: String, required: true },
  },
  schemaOptions,
);

const torrentFileSchema = new Schema<TorrentFileDoc>(
  {
    path: { type: String, required: true },
    sizeBytes: { type: Number, required: true },
    position: { type: Number, required: true },
  },
  { _id: false, versionKey: false },
);

const torrentPreviewFrameSchema = new Schema<TorrentPreviewFrameDoc>(
  {
    key: { type: String, required: true },
    width: { type: Number, required: true },
    height: { type: Number, required: true },
    timestampSeconds: { type: Number, required: true },
  },
  { _id: false, versionKey: false },
);

const torrentPreviewSheetSchema = new Schema<TorrentPreviewSheetDoc>(
  {
    key: { type: String, required: true },
    width: { type: Number, required: true },
    height: { type: Number, required: true },
    mimeType: { type: String, required: true },
  },
  { _id: false, versionKey: false },
);

const torrentPreviewDiagnosticsSchema = new Schema<TorrentPreviewDiagnosticsDoc>(
  {
    artifactVersion: { type: String, default: null },
    artifactFingerprint: { type: String, default: null },
    statusReason: { type: String, default: null },
    downloadedBytes: { type: Number, default: null },
    elapsedSeconds: { type: Number, default: null },
    selectedFilePath: { type: String, default: null },
    selectedFileSizeBytes: { type: Number, default: null },
    warnings: { type: [String], default: [] },
    details: { type: Schema.Types.Mixed, default: {} },
  },
  { _id: false, versionKey: false },
);

const torrentSchema = new Schema<TorrentDoc>(
  {
    _id: { type: String, default: newId },
    infoHash: { type: String, required: true, unique: true },
    name: { type: String, default: null },
    sizeBytes: { type: Number, default: null },
    rawBlobKey: { type: String, default: null },
    metadataStatus: { type: String, enum: ["pending", "processing", "succeeded", "failed"], default: "pending" },
    metadataError: { type: String, default: null },
    metadataFailureKind: { type: String, enum: ["transient", "permanent"], default: null },
    metadataAttempts: { type: Number, default: 0 },
    metadataNextAttemptAt: { type: Date, default: null, index: true },
    metadataLastAttemptAt: { type: Date, default: null },
    metadataStartedAt: { type: Date, default: null },
    metadataFinishedAt: { type: Date, default: null },
    metadataLeaseUntil: { type: Date, default: null, index: true },
    metadataDiagnostics: { type: Schema.Types.Mixed, default: () => ({}) },
    files: { type: [torrentFileSchema], default: [] },
    actorIds: { type: [String], default: [], index: true },
    previewStatus: {
      type: String,
      enum: ["pending", "processing", "succeeded", "partial", "failed"],
      default: "pending",
      index: true,
    },
    previewAttempts: { type: Number, default: 0 },
    previewLastAttemptAt: { type: Date, default: null },
    previewNextAttemptAt: { type: Date, default: null, index: true },
    previewUpdatedAt: { type: Date, default: null },
    previewFrames: { type: [torrentPreviewFrameSchema], default: [] },
    previewSheet: { type: torrentPreviewSheetSchema, default: null },
    previewDiagnostics: { type: torrentPreviewDiagnosticsSchema, default: () => ({}) },
  },
  schemaOptions,
);
torrentSchema.index({ metadataStatus: 1, previewStatus: 1, updatedAt: 1, _id: 1 });

const videoSchema = new Schema<VideoDoc>(
  {
    _id: { type: String, default: newId },
    userId: { type: String, required: true, index: true },
    torrentId: { type: String, required: true, index: true },
    title: { type: String, default: null },
    description: { type: String, default: null },
    rating: { type: Number, default: null },
  },
  schemaOptions,
);
videoSchema.index({ userId: 1, torrentId: 1 }, { unique: true });
videoSchema.index({ userId: 1, createdAt: -1, _id: -1 });

const videoTagSchema = new Schema<VideoTagDoc>(
  {
    _id: { type: String, default: newId },
    videoId: { type: String, required: true, index: true },
    tagId: { type: String, required: true, index: true },
    createdAt: { type: Date, default: Date.now },
  },
  { versionKey: false },
);
videoTagSchema.index({ videoId: 1, tagId: 1 }, { unique: true });

export const UserModel = model<UserDoc>("User", userSchema);
export const AccountModel = model<AccountDoc>("Account", accountSchema);
export const SessionModel = model<SessionDoc>("Session", sessionSchema);
export const VerificationTokenModel = model<VerificationTokenDoc>("VerificationToken", verificationTokenSchema);
export const TagModel = model<TagDoc>("Tag", tagSchema);
export const ActorModel = model<ActorDoc>("Actor", actorSchema);
export const TorrentModel = model<TorrentDoc>("Torrent", torrentSchema);
export const VideoModel = model<VideoDoc>("Video", videoSchema);
export const VideoTagModel = model<VideoTagDoc>("VideoTag", videoTagSchema);

export const db = {
  mongoose,
  User: UserModel,
  Account: AccountModel,
  Session: SessionModel,
  VerificationToken: VerificationTokenModel,
  Tag: TagModel,
  Actor: ActorModel,
  Torrent: TorrentModel,
  Video: VideoModel,
  VideoTag: VideoTagModel,
  connect: connectMongo,
  disconnect: disconnectMongo,
  ensureIndexes,
};

export function newId() {
  return randomUUID();
}

export function accountId(provider: string, providerAccountId: string) {
  return `${provider}:${providerAccountId}`;
}

export function sessionId(sessionToken: string) {
  return sessionToken;
}

export function verificationTokenId(identifier: string, token: string) {
  return `${identifier}:${token}`;
}

export function videoTagId(videoId: string, tagId: string) {
  return `${videoId}:${tagId}`;
}

export async function connectMongo() {
  const isCurrentInstance = globalForMongoose.mongooseInstance === mongoose;
  const isDisconnected = mongoose.connection.readyState === 0 || mongoose.connection.readyState === 3;
  if (!globalForMongoose.mongooseConnection || !isCurrentInstance || isDisconnected) {
    const env = getDatabaseEnv();
    globalForMongoose.mongooseInstance = mongoose;
    globalForMongoose.mongooseConnection = mongoose
      .connect(env.mongodbUri, {
        dbName: env.mongodbDatabase,
        serverSelectionTimeoutMS: env.mongodbServerSelectionTimeoutMs,
      })
      .catch((error) => {
        if (globalForMongoose.mongooseInstance === mongoose) {
          globalForMongoose.mongooseConnection = undefined;
          globalForMongoose.mongooseInstance = undefined;
        }
        throw error;
      });
  }
  return globalForMongoose.mongooseConnection;
}

export async function disconnectMongo() {
  globalForMongoose.mongooseConnection = undefined;
  globalForMongoose.mongooseInstance = undefined;
  await mongoose.disconnect();
}

export async function ensureIndexes() {
  await connectMongo();
  await Promise.all([
    UserModel.init(),
    AccountModel.init(),
    SessionModel.init(),
    VerificationTokenModel.init(),
    TagModel.init(),
    ActorModel.init(),
    TorrentModel.init(),
    VideoModel.init(),
    VideoTagModel.init(),
  ]);
}

export async function getAccountAccessToken(userId: string, provider: string) {
  await connectMongo();
  const account = await AccountModel.findOne({ userId, provider }).lean().exec();
  return account?.access_token ?? null;
}

export async function updateUserProfile(
  userId: string,
  data: Pick<UserDoc, "entraOid" | "isAdmin" | "name" | "email" | "image">,
) {
  await connectMongo();
  return UserModel.findByIdAndUpdate(
    userId,
    {
      $set: data,
      $setOnInsert: {
        _id: userId,
        emailVerified: null,
      },
    },
    { new: true, upsert: true },
  )
    .lean()
    .exec();
}

export async function resetE2EState(usernames: string[]) {
  await connectMongo();
  const displayNames = usernames.map((username) => username.split("@")[0] ?? username);
  const users = await UserModel.find({
    $or: [{ email: { $in: usernames } }, { name: { $in: displayNames } }],
  })
    .lean()
    .exec();

  const userIds = users.map((user) => user._id);
  const videos = await VideoModel.find({ userId: { $in: userIds } }).lean().exec();
  const candidateTorrentIds = [...new Set(videos.map((video) => video.torrentId))];
  const staleActors = await ActorModel.find({ name: /^e2e-actor-/ }).lean().exec();
  const staleActorIds = staleActors.map((actor) => actor._id);

  await Promise.all([
    staleActorIds.length > 0 ? ActorModel.deleteMany({ _id: { $in: staleActorIds } }).exec() : Promise.resolve(),
    staleActorIds.length > 0 ? TorrentModel.updateMany({}, { $pull: { actorIds: { $in: staleActorIds } } }).exec() : Promise.resolve(),
    TagModel.deleteMany({ name: /^e2e-tag-/ }).exec(),
    userIds.length > 0 ? UserModel.deleteMany({ _id: { $in: userIds } }).exec() : Promise.resolve(),
    userIds.length > 0 ? AccountModel.deleteMany({ userId: { $in: userIds } }).exec() : Promise.resolve(),
    userIds.length > 0 ? SessionModel.deleteMany({ userId: { $in: userIds } }).exec() : Promise.resolve(),
    userIds.length > 0 ? VideoModel.deleteMany({ userId: { $in: userIds } }).exec() : Promise.resolve(),
    videos.length > 0 ? VideoTagModel.deleteMany({ videoId: { $in: videos.map((video) => video._id) } }).exec() : Promise.resolve(),
  ]);

  const blobKeys: string[] = staleActors
    .map((actor) => actor.profileImageKey)
    .filter((key): key is string => Boolean(key));

  for (const torrentId of candidateTorrentIds) {
    const remainingVideos = await VideoModel.countDocuments({ torrentId }).exec();
    if (remainingVideos > 0) {
      continue;
    }
    const torrent = await TorrentModel.findById(torrentId).lean().exec();
    blobKeys.push(...torrentBlobKeys(torrent));
    await TorrentModel.deleteOne({ _id: torrentId }).exec();
  }

  return { blobKeys, rawBlobKeys: blobKeys };
}

function torrentBlobKeys(torrent: TorrentDoc | null): string[] {
  if (!torrent) {
    return [];
  }
  return [
    torrent.rawBlobKey,
    torrent.previewSheet?.key,
    ...(torrent.previewFrames ?? []).map((frame) => frame.key),
  ].filter((key): key is string => Boolean(key));
}

function model<T>(name: string, schema: Schema<T>): Model<T> {
  return (mongoose.models[name] as Model<T> | undefined) ?? mongoose.model<T>(name, schema);
}
