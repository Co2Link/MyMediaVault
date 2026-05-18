import { notFound, redirect } from "next/navigation";
import { auth } from "@/auth";
import { getVideoPreviewArtifact } from "@/lib/videos";
import { NotFoundError } from "@/lib/errors";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: {
    params: Promise<{ id: string; artifact: string }>;
  },
) {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }

  const { id, artifact } = await context.params;
  const requestedArtifact = parseArtifact(artifact);
  if (!requestedArtifact) {
    notFound();
  }

  try {
    const result = await getVideoPreviewArtifact(session.user.id, id, requestedArtifact);
    return new Response(toArrayBuffer(result.bytes), {
      headers: {
        "Cache-Control": "private, max-age=300",
        "Content-Type": result.mimeType,
      },
    });
  } catch (error) {
    if (error instanceof NotFoundError) {
      notFound();
    }
    throw error;
  }
}

function toArrayBuffer(bytes: Uint8Array) {
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  return buffer;
}

function parseArtifact(artifact: string) {
  if (artifact === "sheet") {
    return "sheet" as const;
  }

  const match = /^frame-(\d+)$/.exec(artifact);
  if (!match) {
    return null;
  }

  const frameIndex = Number(match[1]);
  if (!Number.isSafeInteger(frameIndex) || frameIndex < 0) {
    return null;
  }
  return { frameIndex };
}
