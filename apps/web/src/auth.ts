import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id";
import NextAuth from "next-auth";
import { MongooseAuthAdapter } from "@mymediavault/core/auth-adapter";
import { updateUserProfile } from "@/lib/db";
import { getEnv } from "@/lib/env";

const env = getEnv();

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: MongooseAuthAdapter(),
  session: {
    strategy: "database",
  },
  trustHost: true,
  secret: env.authSecret,
  pages: {
    signIn: "/auth/sign-in",
  },
  providers: [
    MicrosoftEntraID({
      clientId: env.authClientId,
      clientSecret: env.authClientSecret,
      issuer: env.authIssuer,
      client: {
        token_endpoint_auth_method: "client_secret_post",
      },
      authorization: {
        params: {
          scope: "openid profile email offline_access User.Read",
          prompt: "select_account",
        },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, profile }) {
      if (profile && typeof profile === "object") {
        const entraProfile = profile as {
          oid?: string;
          sub?: string;
          picture?: string;
        };
        token.entraOid = entraProfile.oid ?? entraProfile.sub;
        token.picture = entraProfile.picture;
      }
      return token;
    },
    async session({ session, user, token }) {
      const typedSession = session as typeof session & {
        user: typeof session.user & {
          id: string;
          entraOid: string | null;
          isAdmin: boolean;
        };
      };
      typedSession.user.id = user.id;
      typedSession.user.entraOid = user.entraOid;
      typedSession.user.isAdmin = user.isAdmin;
      if (token?.picture && !typedSession.user.image) {
        typedSession.user.image = token.picture as string;
      }
      return typedSession;
    },
    async signIn() {
      return true;
    },
  },
  events: {
    async signIn({ account, profile, user }) {
      const entraProfile = profile as
        | {
            oid?: string;
            sub?: string;
            groups?: string[];
            name?: string;
            preferred_username?: string;
            email?: string;
          }
        | undefined;
      const entraOid = entraProfile?.oid ?? entraProfile?.sub ?? null;
      const email = entraProfile?.preferred_username ?? entraProfile?.email ?? user.email;
      const isAdmin = await resolveAdminStatus(entraOid, entraProfile?.groups ?? [], account?.access_token ?? null);
      const userId = user.id ?? user.email;
      if (!userId) {
        throw new Error("Authenticated user is missing an identifier.");
      }

      await updateUserProfile(userId, {
        entraOid,
        isAdmin,
        name: entraProfile?.name ?? user.name ?? null,
        email: email ?? null,
        image: user.image ?? null,
      });
    },
  },
});

async function resolveAdminStatus(entraOid: string | null, groups: string[], accessToken: string | null) {
  if (entraOid && env.adminObjectIds.includes(entraOid)) {
    return true;
  }
  if (groups.some((group) => env.adminGroupObjectIds.includes(group))) {
    return true;
  }
  if (env.adminGroupObjectIds.length === 0 || !accessToken) {
    return false;
  }
  return checkAdminGroupMembership(accessToken);
}

async function checkAdminGroupMembership(accessToken: string) {
  const response = await fetch("https://graph.microsoft.com/v1.0/me/checkMemberGroups", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      groupIds: env.adminGroupObjectIds,
    }),
  });
  if (!response.ok) {
    return false;
  }
  const matchingGroups = (await response.json()) as { value?: unknown };
  return Array.isArray(matchingGroups.value)
    ? matchingGroups.value.some((groupId) => typeof groupId === "string" && env.adminGroupObjectIds.includes(groupId))
    : false;
}
