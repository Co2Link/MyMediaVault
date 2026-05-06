import { auth } from "@/auth";
import { db } from "@/lib/db";

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  const account = await db.account.findFirst({
    where: { userId: session.user.id, provider: "microsoft-entra-id" },
    select: { access_token: true },
  });
  if (!account?.access_token) {
    return new Response("Not found", { status: 404 });
  }

  const response = await fetch("https://graph.microsoft.com/v1.0/me/photo/$value", {
    headers: {
      Authorization: `Bearer ${account.access_token}`,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    return new Response("Not found", { status: response.status === 404 ? 404 : 502 });
  }

  return new Response(await response.arrayBuffer(), {
    headers: {
      "Content-Type": response.headers.get("content-type") ?? "image/jpeg",
      "Cache-Control": "private, max-age=300",
    },
  });
}
