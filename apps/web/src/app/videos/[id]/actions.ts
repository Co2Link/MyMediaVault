"use server";

import { revalidatePath } from "next/cache";
import { AppError } from "@/lib/errors";
import { getRequiredSession } from "@/lib/auth/session";
import { updateVideo } from "@/lib/videos";
import { normalizeOptionalText, normalizeRating, videoUpdateSchema } from "@/lib/validation";

export type UpdateVideoActionState = {
  error: string | null;
  success: string | null;
};

export async function updateVideoAction(
  videoId: string,
  _: UpdateVideoActionState,
  formData: FormData,
): Promise<UpdateVideoActionState> {
  try {
    const session = await getRequiredSession();
    const parsed = videoUpdateSchema.parse({
      title: formData.get("title"),
      description: formData.get("description"),
      rating: formData.get("rating"),
    });
    await updateVideo(session.user.id, videoId, {
      title: normalizeOptionalText(parsed.title),
      description: normalizeOptionalText(parsed.description),
      rating: normalizeRating(parsed.rating),
    });
    revalidatePath("/");
    revalidatePath(`/videos/${videoId}`);
    return { error: null, success: "Video details saved." };
  } catch (error) {
    if (error instanceof AppError) {
      return { error: error.message, success: null };
    }
    if (error instanceof Error) {
      return { error: error.message, success: null };
    }
    return { error: "Unable to save video.", success: null };
  }
}
