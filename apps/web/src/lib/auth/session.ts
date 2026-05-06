import { cache } from "react";
import { auth } from "@/auth";
import { ForbiddenError } from "@/lib/errors";

export type AppSession = Awaited<ReturnType<typeof auth>> & {
  user: {
    id: string;
    email?: string | null;
    name?: string | null;
    image?: string | null;
    entraOid?: string | null;
    isAdmin?: boolean;
  };
};

export const getRequiredSession = cache(async (): Promise<AppSession> => {
  const session = (await auth()) as AppSession | null;
  if (!session?.user?.id) {
    throw new ForbiddenError("Authentication is required.");
  }
  return session;
});

export async function requireAdminSession() {
  const session = await getRequiredSession();
  if (!session.user.isAdmin) {
    throw new ForbiddenError("Administrator access is required.");
  }
  return session;
}
