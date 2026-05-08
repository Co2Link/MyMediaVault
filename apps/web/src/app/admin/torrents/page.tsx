import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { TorrentAdminPanel } from "@/app/admin/torrents/torrent-admin-panel";
import { listTorrents } from "@/lib/videos";

export default async function AdminTorrentsPage() {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }
  if (!session.user.isAdmin) {
    return (
      <main className="workspace">
        <section className="editor-card">
          <h1>Torrents</h1>
          <p className="error-copy">Administrator access is required.</p>
        </section>
      </main>
    );
  }

  const torrents = await listTorrents();

  return (
    <main className="workspace">
      <TorrentAdminPanel torrents={torrents} />
    </main>
  );
}
