"use server";

import { revalidatePath } from "next/cache";
import { requireAdminSession } from "@/lib/auth/session";
import { AppError } from "@/lib/errors";
import { createTag, deleteTag, updateTag } from "@/lib/tags";
import { tagSchema } from "@/lib/validation";

export type TagActionState = { error: string | null };

export async function createTagAction(_: TagActionState, formData: FormData): Promise<TagActionState> {
  try {
    await requireAdminSession();
    const parsed = tagSchema.parse({ name: formData.get("name") });
    await createTag(parsed.name);
    revalidatePath("/admin/tags");
    return { error: null };
  } catch (error) {
    if (error instanceof AppError) {
      return { error: error.message };
    }
    if (error instanceof Error) {
      return { error: error.message };
    }
    return { error: "Unable to create tag." };
  }
}

export async function renameTagAction(tagId: string, formData: FormData) {
  await requireAdminSession();
  const parsed = tagSchema.parse({ name: formData.get("name") });
  await updateTag(tagId, parsed.name);
  revalidatePath("/admin/tags");
}

export async function deleteTagAction(tagId: string) {
  await requireAdminSession();
  await deleteTag(tagId);
  revalidatePath("/admin/tags");
}
