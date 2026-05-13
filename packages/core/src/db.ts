import { randomUUID } from "node:crypto";
import mongoose, { Schema, type Model } from "mongoose";
import { getDatabaseEnv } from "./env.js";
import type { JobStatus, MetadataStatus } from "./types.js";

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

export type TorrentFileDoc = {
  path: string;
  sizeBytes: number;
  position: number;
};

export type TorrentDoc = {
  _id: string;
  infoHash: string;
  name: string | null;
  sizeBytes: number | null;
  rawBlobKey: string | null;
  metadataStatus: MetadataStatus;
  metadataError: string | null;
  metadataAttempts: number;
  metadataLastAttemptAt: Date | null;
  files: TorrentFileDoc[];
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

export type TorrentMetadataJobDoc = {
  _id: string;
  torrentId: string;
  status: JobStatus;
  attempt: number;
  error: string | null;
  queueEnqueuedAt: Date;
  lastDequeuedAt: Date | null;
  startedAt: Date | null;
  finishedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
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

const torrentFileSchema = new Schema<TorrentFileDoc>(
  {
    path: { type: String, required: true },
    sizeBytes: { type: Number, required: true },
    position: { type: Number, required: true },
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
    metadataAttempts: { type: Number, default: 0 },
    metadataLastAttemptAt: { type: Date, default: null },
    files: { type: [torrentFileSchema], default: [] },
  },
  schemaOptions,
);

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

const torrentMetadataJobSchema = new Schema<TorrentMetadataJobDoc>(
  {
    _id: { type: String, default: newId },
    torrentId: { type: String, required: true, index: true },
    status: {
      type: String,
      enum: ["queued", "processing", "succeeded", "failed"],
      required: true,
      index: true,
    },
    attempt: { type: Number, required: true },
    error: { type: String, default: null },
    queueEnqueuedAt: { type: Date, default: Date.now },
    lastDequeuedAt: { type: Date, default: null },
    startedAt: { type: Date, default: null },
    finishedAt: { type: Date, default: null },
  },
  schemaOptions,
);
torrentMetadataJobSchema.index({ torrentId: 1, status: 1 });
torrentMetadataJobSchema.index({ status: 1, createdAt: 1, _id: 1 });

export const UserModel = model<UserDoc>("User", userSchema);
export const AccountModel = model<AccountDoc>("Account", accountSchema);
export const SessionModel = model<SessionDoc>("Session", sessionSchema);
export const VerificationTokenModel = model<VerificationTokenDoc>("VerificationToken", verificationTokenSchema);
export const TagModel = model<TagDoc>("Tag", tagSchema);
export const TorrentModel = model<TorrentDoc>("Torrent", torrentSchema);
export const VideoModel = model<VideoDoc>("Video", videoSchema);
export const VideoTagModel = model<VideoTagDoc>("VideoTag", videoTagSchema);
export const TorrentMetadataJobModel = model<TorrentMetadataJobDoc>("TorrentMetadataJob", torrentMetadataJobSchema);

export const db = {
  mongoose,
  User: UserModel,
  Account: AccountModel,
  Session: SessionModel,
  VerificationToken: VerificationTokenModel,
  Tag: TagModel,
  Torrent: TorrentModel,
  Video: VideoModel,
  VideoTag: VideoTagModel,
  TorrentMetadataJob: TorrentMetadataJobModel,
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
    TorrentModel.init(),
    VideoModel.init(),
    VideoTagModel.init(),
    TorrentMetadataJobModel.init(),
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

  await Promise.all([
    TagModel.deleteMany({ name: /^e2e-tag-/ }).exec(),
    userIds.length > 0 ? UserModel.deleteMany({ _id: { $in: userIds } }).exec() : Promise.resolve(),
    userIds.length > 0 ? AccountModel.deleteMany({ userId: { $in: userIds } }).exec() : Promise.resolve(),
    userIds.length > 0 ? SessionModel.deleteMany({ userId: { $in: userIds } }).exec() : Promise.resolve(),
    userIds.length > 0 ? VideoModel.deleteMany({ userId: { $in: userIds } }).exec() : Promise.resolve(),
    videos.length > 0 ? VideoTagModel.deleteMany({ videoId: { $in: videos.map((video) => video._id) } }).exec() : Promise.resolve(),
  ]);

  const rawBlobKeys: string[] = [];
  for (const torrentId of candidateTorrentIds) {
    const remainingVideos = await VideoModel.countDocuments({ torrentId }).exec();
    if (remainingVideos > 0) {
      continue;
    }
    const torrent = await TorrentModel.findById(torrentId).lean().exec();
    if (torrent?.rawBlobKey) {
      rawBlobKeys.push(torrent.rawBlobKey);
    }
    await Promise.all([
      TorrentModel.deleteOne({ _id: torrentId }).exec(),
      TorrentMetadataJobModel.deleteMany({ torrentId }).exec(),
    ]);
  }

  return { rawBlobKeys };
}

function model<T>(name: string, schema: Schema<T>): Model<T> {
  return (mongoose.models[name] as Model<T> | undefined) ?? mongoose.model<T>(name, schema);
}
