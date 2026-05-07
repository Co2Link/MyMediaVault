import type { Adapter, AdapterAccount, AdapterSession, AdapterUser, VerificationToken } from "@auth/core/adapters";
import {
  AccountModel,
  SessionModel,
  UserModel,
  VerificationTokenModel,
  accountId,
  connectMongo,
  newId,
  sessionId,
  verificationTokenId,
  type AccountDoc,
  type SessionDoc,
  type UserDoc,
  type VerificationTokenDoc,
} from "./db.js";

export function MongooseAuthAdapter(): Adapter {
  return {
    async createUser(user) {
      await connectMongo();
      const id = user.id ?? newId();
      const created = await UserModel.findByIdAndUpdate(
        id,
        {
          $setOnInsert: {
            _id: id,
            name: user.name ?? null,
            email: user.email ?? null,
            emailVerified: user.emailVerified ?? null,
            image: user.image ?? null,
            entraOid: null,
            isAdmin: false,
          },
        },
        { new: true, upsert: true, setDefaultsOnInsert: true },
      )
        .lean()
        .exec();
      if (!created) {
        throw new Error("Unable to create user.");
      }
      return toAdapterUser(created);
    },
    async getUser(id) {
      await connectMongo();
      const user = await UserModel.findById(id).lean().exec();
      return user ? toAdapterUser(user) : null;
    },
    async getUserByEmail(email) {
      await connectMongo();
      const user = await UserModel.findOne({ email }).lean().exec();
      return user ? toAdapterUser(user) : null;
    },
    async getUserByAccount({ provider, providerAccountId }) {
      await connectMongo();
      const account = await AccountModel.findById(accountId(provider, providerAccountId)).lean().exec();
      if (!account) {
        return null;
      }
      const user = await UserModel.findById(account.userId).lean().exec();
      return user ? toAdapterUser(user) : null;
    },
    async updateUser(user) {
      await connectMongo();
      const updated = await UserModel.findByIdAndUpdate(
        user.id,
        {
          $set: {
            ...(user.name !== undefined ? { name: user.name } : {}),
            ...(user.email !== undefined ? { email: user.email } : {}),
            ...(user.emailVerified !== undefined ? { emailVerified: user.emailVerified } : {}),
            ...(user.image !== undefined ? { image: user.image } : {}),
          },
        },
        { new: true },
      )
        .lean()
        .exec();
      if (!updated) {
        throw new Error("User not found.");
      }
      return toAdapterUser(updated);
    },
    async deleteUser(userId) {
      await connectMongo();
      await Promise.all([
        UserModel.deleteOne({ _id: userId }).exec(),
        AccountModel.deleteMany({ userId }).exec(),
        SessionModel.deleteMany({ userId }).exec(),
      ]);
    },
    async linkAccount(account) {
      await connectMongo();
      await AccountModel.findByIdAndUpdate(
        accountId(account.provider, account.providerAccountId),
        {
          $set: {
            ...account,
            _id: accountId(account.provider, account.providerAccountId),
          },
        },
        { upsert: true, new: true, setDefaultsOnInsert: true },
      ).exec();
      return account;
    },
    async unlinkAccount({ provider, providerAccountId }) {
      await connectMongo();
      const account = await AccountModel.findByIdAndDelete(accountId(provider, providerAccountId)).lean().exec();
      return account ? toAdapterAccount(account) : undefined;
    },
    async getAccount(providerAccountId, provider) {
      await connectMongo();
      const account = await AccountModel.findById(accountId(provider, providerAccountId)).lean().exec();
      return account ? toAdapterAccount(account) : null;
    },
    async createSession(session) {
      await connectMongo();
      const created = await SessionModel.create({
        _id: sessionId(session.sessionToken),
        sessionToken: session.sessionToken,
        userId: session.userId,
        expires: session.expires,
      });
      return toAdapterSession(created.toObject());
    },
    async getSessionAndUser(sessionToken) {
      await connectMongo();
      const session = await SessionModel.findById(sessionId(sessionToken)).lean().exec();
      if (!session) {
        return null;
      }
      const user = await UserModel.findById(session.userId).lean().exec();
      if (!user) {
        return null;
      }
      return {
        session: toAdapterSession(session),
        user: toAdapterUser(user),
      };
    },
    async updateSession(session) {
      await connectMongo();
      const updated = await SessionModel.findByIdAndUpdate(
        sessionId(session.sessionToken),
        { $set: { ...(session.expires ? { expires: session.expires } : {}) } },
        { new: true },
      )
        .lean()
        .exec();
      return updated ? toAdapterSession(updated) : null;
    },
    async deleteSession(sessionToken) {
      await connectMongo();
      const deleted = await SessionModel.findByIdAndDelete(sessionId(sessionToken)).lean().exec();
      return deleted ? toAdapterSession(deleted) : null;
    },
    async createVerificationToken(token) {
      await connectMongo();
      const created = await VerificationTokenModel.create({
        _id: verificationTokenId(token.identifier, token.token),
        identifier: token.identifier,
        token: token.token,
        expires: token.expires,
      });
      return toVerificationToken(created.toObject());
    },
    async useVerificationToken({ identifier, token }) {
      await connectMongo();
      const deleted = await VerificationTokenModel.findByIdAndDelete(verificationTokenId(identifier, token))
        .lean()
        .exec();
      return deleted ? toVerificationToken(deleted) : null;
    },
  };
}

function toAdapterUser(user: UserDoc): AdapterUser {
  return {
    id: user._id,
    name: user.name,
    email: user.email,
    emailVerified: user.emailVerified,
    image: user.image,
    entraOid: user.entraOid,
    isAdmin: user.isAdmin,
  } as AdapterUser;
}

function toAdapterAccount(account: AccountDoc): AdapterAccount {
  const { _id: _id, createdAt: _createdAt, updatedAt: _updatedAt, ...adapterAccount } = account;
  return adapterAccount as AdapterAccount;
}

function toAdapterSession(session: SessionDoc): AdapterSession {
  return {
    sessionToken: session.sessionToken,
    userId: session.userId,
    expires: session.expires,
  };
}

function toVerificationToken(token: VerificationTokenDoc): VerificationToken {
  return {
    identifier: token.identifier,
    token: token.token,
    expires: token.expires,
  };
}
