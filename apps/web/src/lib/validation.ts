import { z } from "zod";

export const videoCreateSchema = z.object({
  infoHash: z.string().min(1),
  title: z.string().trim().max(300).optional().or(z.literal("")),
  description: z.string().trim().max(5000).optional().or(z.literal("")),
  rating: z.union([z.literal(""), z.coerce.number().int().min(1).max(5)]).optional(),
});

export const videoUpdateSchema = z.object({
  title: z.string().trim().max(300).optional().or(z.literal("")),
  description: z.string().trim().max(5000).optional().or(z.literal("")),
  rating: z.union([z.literal(""), z.coerce.number().int().min(1).max(5)]).optional(),
});

export const tagSchema = z.object({
  name: z.string().trim().min(1).max(128),
});

export function normalizeInfoHash(value: string) {
  const normalized = value.trim().toLowerCase();
  if (!/^[0-9a-f]{40}$/.test(normalized)) {
    throw new Error("Info hash must be a 40-character hexadecimal string.");
  }
  return normalized;
}

export function normalizeOptionalText(value: string | undefined) {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function normalizeRating(value: "" | number | undefined) {
  return typeof value === "number" ? value : null;
}
