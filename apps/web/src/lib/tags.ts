import { db } from "@/lib/db";
import { ConflictError, NotFoundError } from "@/lib/errors";

export async function listTags() {
  return db.tag.findMany({
    orderBy: { name: "asc" },
  });
}

export async function createTag(name: string) {
  const normalized = normalizeName(name);
  const existing = await db.tag.findUnique({ where: { name: normalized } });
  if (existing) {
    throw new ConflictError("Tag name already exists.");
  }
  return db.tag.create({ data: { name: normalized } });
}

export async function updateTag(id: string, name: string) {
  const normalized = normalizeName(name);
  const tag = await db.tag.findUnique({ where: { id } });
  if (!tag) {
    throw new NotFoundError("Tag was not found.");
  }
  const existing = await db.tag.findFirst({
    where: { name: normalized, id: { not: id } },
  });
  if (existing) {
    throw new ConflictError("Tag name already exists.");
  }
  return db.tag.update({
    where: { id },
    data: { name: normalized },
  });
}

export async function deleteTag(id: string) {
  const tag = await db.tag.findUnique({ where: { id } });
  if (!tag) {
    throw new NotFoundError("Tag was not found.");
  }
  await db.tag.delete({ where: { id } });
}

function normalizeName(name: string) {
  const normalized = name.trim().replace(/\s+/g, " ");
  if (!normalized) {
    throw new ConflictError("Tag name is required.");
  }
  return normalized;
}
