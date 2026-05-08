"use server";

import { revalidatePath } from "next/cache";
import { requireAdminSession } from "@/lib/auth/session";
import { deleteTorrent } from "@/lib/videos";

export async function deleteTorrentAction(torrentId: string) {
  await requireAdminSession();
  await deleteTorrent(torrentId);
  revalidatePath("/");
  revalidatePath("/admin/torrents");
}
