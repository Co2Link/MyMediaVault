import { notFound, redirect } from "next/navigation";
import { auth } from "@/auth";
import { AppError } from "@/lib/errors";
import { getActorProfileImage } from "@/lib/actors";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: {
    params: Promise<{ id: string }>;
  },
) {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }

  const { id } = await context.params;
  try {
    const result = await getActorProfileImage(id);
    return new Response(toArrayBuffer(result.bytes), {
      headers: {
        "Cache-Control": "private, max-age=300",
        "Content-Type": result.mimeType,
      },
    });
  } catch (error) {
    if (error instanceof AppError) {
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
