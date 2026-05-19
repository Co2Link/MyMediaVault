"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { getRequiredSession } from "@/lib/auth/session";
import { AppError } from "@/lib/errors";
import { createVideo } from "@/lib/videos";
import { normalizeOptionalText, normalizeRating, videoCreateSchema } from "@/lib/validation";

export type AddVideoActionState = {
  error: string | null;
};

export async function addVideoAction(_: AddVideoActionState, formData: FormData): Promise<AddVideoActionState> {
  let videoId: string | null = null;
  try {
    const session = await getRequiredSession();
    const parsed = videoCreateSchema.parse({
      infoHash: formData.get("infoHash"),
      title: formData.get("title"),
      description: formData.get("description"),
      rating: formData.get("rating"),
      tagIds: formData.getAll("tagIds"),
      actorIds: formData.getAll("actorIds"),
    });
    const video = await createVideo(session.user.id, {
      infoHash: parsed.infoHash,
      title: normalizeOptionalText(parsed.title),
      description: normalizeOptionalText(parsed.description),
      rating: normalizeRating(parsed.rating),
      tagIds: parsed.tagIds,
      actorIds: parsed.actorIds,
    });
    videoId = video.id;
    revalidatePath("/");
  } catch (error) {
    if (error instanceof AppError) {
      return { error: error.message };
    }
    if (error instanceof Error) {
      return { error: error.message };
    }
    return { error: "Unable to add video." };
  }
  redirect(`/videos/${videoId}?created=1`);
}
