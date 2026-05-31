import { auth } from "@/auth";
import { getAccountAccessToken } from "@/lib/db";

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  const accessToken = await getAccountAccessToken(session.user.id, "microsoft-entra-id");
  if (!accessToken) {
    return avatarFallback(session.user.name);
  }

  try {
    const response = await fetch("https://graph.microsoft.com/v1.0/me/photo/$value", {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      cache: "no-store",
    });
    if (!response.ok) {
      return avatarFallback(session.user.name);
    }

    return new Response(await response.arrayBuffer(), {
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "image/jpeg",
        "Cache-Control": "private, max-age=300",
      },
    });
  } catch {
    return avatarFallback(session.user.name);
  }
}

function avatarFallback(name: string | null | undefined) {
  const initial = (name ?? "User").trim().charAt(0).toUpperCase() || "U";
  const escapedInitial = initial.replace(/[&<>"']/g, (character) => `&#${character.charCodeAt(0)};`);
  const svg = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">',
    '<circle cx="20" cy="20" r="20" fill="#f5d9c9"/>',
    `<text x="20" y="25" fill="#ab4418" font-family="monospace" font-size="16" text-anchor="middle">${escapedInitial}</text>`,
    "</svg>",
  ].join("");

  return new Response(svg, {
    headers: {
      "Content-Type": "image/svg+xml; charset=utf-8",
      "Cache-Control": "private, max-age=300",
    },
  });
}
