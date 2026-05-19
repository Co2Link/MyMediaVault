"use server";

import { revalidatePath } from "next/cache";
import { requireAdminSession } from "@/lib/auth/session";
import { createActor, deleteActor, updateActor, type ActorImageInput } from "@/lib/actors";
import { AppError } from "@/lib/errors";
import { actorSchema, normalizeOptionalText } from "@/lib/validation";

export type ActorActionState = { error: string | null };

export async function createActorAction(_: ActorActionState, formData: FormData): Promise<ActorActionState> {
  try {
    await requireAdminSession();
    const parsed = actorSchema.parse({
      name: formData.get("name"),
      description: formData.get("description"),
    });
    await createActor({
      name: parsed.name,
      description: normalizeOptionalText(parsed.description),
      image: await requiredImageFromFormData(formData),
    });
    revalidateActorPaths();
    return { error: null };
  } catch (error) {
    return { error: actionErrorMessage(error, "Unable to create actor.") };
  }
}

export async function updateActorAction(actorId: string, formData: FormData) {
  await requireAdminSession();
  const parsed = actorSchema.parse({
    name: formData.get("name"),
    description: formData.get("description"),
  });
  await updateActor(actorId, {
    name: parsed.name,
    description: normalizeOptionalText(parsed.description),
    image: await optionalImageFromFormData(formData),
  });
  revalidateActorPaths(actorId);
}

export async function deleteActorAction(actorId: string) {
  await requireAdminSession();
  await deleteActor(actorId);
  revalidateActorPaths(actorId);
}

async function requiredImageFromFormData(formData: FormData) {
  const image = await optionalImageFromFormData(formData);
  if (!image) {
    throw new Error("Profile image is required.");
  }
  return image;
}

async function optionalImageFromFormData(formData: FormData): Promise<ActorImageInput | null> {
  const file = formData.get("profileImage");
  if (!(file instanceof File) || file.size === 0) {
    return null;
  }
  return {
    bytes: new Uint8Array(await file.arrayBuffer()),
    mimeType: file.type,
  };
}

function revalidateActorPaths(actorId?: string) {
  revalidatePath("/");
  revalidatePath("/add");
  revalidatePath("/admin/actors");
  revalidatePath("/videos/[id]", "page");
  if (actorId) {
    revalidatePath(`/actors/${actorId}`);
    revalidatePath(`/api/actors/${actorId}/image`);
  }
}

function actionErrorMessage(error: unknown, fallback: string) {
  if (error instanceof AppError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}
