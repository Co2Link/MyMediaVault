"use server";

import { revalidatePath } from "next/cache";
import { requireAdminSession } from "@/lib/auth/session";
import { deleteTorrent, resetTorrentPreview } from "@/lib/videos";

export async function deleteTorrentAction(torrentId: string) {
  await requireAdminSession();
  await deleteTorrent(torrentId);
  revalidatePath("/");
  revalidatePath("/admin/torrents");
}

export async function retryTorrentPreviewAction(torrentId: string) {
  await requireAdminSession();
  await resetTorrentPreview(torrentId);
  revalidatePath("/");
  revalidatePath("/admin/torrents");
}
