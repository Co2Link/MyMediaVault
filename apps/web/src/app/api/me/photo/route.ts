import { auth } from "@/auth";
import { getAccountAccessToken } from "@/lib/db";

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  const accessToken = await getAccountAccessToken(session.user.id, "microsoft-entra-id");
  if (!accessToken) {
    return new Response("Not found", { status: 404 });
  }

  const response = await fetch("https://graph.microsoft.com/v1.0/me/photo/$value", {
    headers: {
      Authorization: `Bearer ${accessToken}`,
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
