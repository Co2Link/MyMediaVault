"use server";

import { revalidatePath } from "next/cache";
import { requireAdminSession } from "@/lib/auth/session";
import { cancelTorrentProcessing, deleteTorrent, queueTorrentProcessing, resetTorrentActorAnalysis } from "@/lib/videos";

export async function deleteTorrentAction(torrentId: string) {
  await requireAdminSession();
  await deleteTorrent(torrentId);
  revalidatePath("/");
  revalidatePath("/admin/torrents");
}

export async function queueTorrentProcessingAction(torrentId: string) {
  await requireAdminSession();
  await queueTorrentProcessing(torrentId);
  revalidatePath("/");
  revalidatePath("/admin/torrents");
}

export async function cancelTorrentProcessingAction(torrentId: string) {
  await requireAdminSession();
  await cancelTorrentProcessing(torrentId);
  revalidatePath("/");
  revalidatePath("/admin/torrents");
}

export async function reanalyzeTorrentActorsAction(torrentId: string) {
  await requireAdminSession();
  await resetTorrentActorAnalysis(torrentId);
  revalidatePath("/");
  revalidatePath("/admin/torrents");
}
