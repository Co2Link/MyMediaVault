import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { TorrentAdminPanel } from "@/app/admin/torrents/torrent-admin-panel";
import { AdminCatalogFilter } from "@/components/admin-catalog-filter";
import { PaginationLinks } from "@/components/pagination-links";
import { firstQueryValue, paginate } from "@/lib/pagination";
import { listTorrents } from "@/lib/videos";

export default async function AdminTorrentsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string | string[]; q?: string | string[] }>;
}) {
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

  const query = await searchParams;
  const q = firstQueryValue(query.q)?.trim() ?? "";
  const normalizedQuery = q.toLowerCase();
  const torrents = (await listTorrents()).filter((torrent) =>
    [torrent.name, torrent.infoHash, torrent.processingState, torrent.preview.status, torrent.actorAnalysis.status].some(
      (value) => value?.toLowerCase().includes(normalizedQuery),
    ),
  );
  const page = paginate(torrents, firstQueryValue(query.page), 8);

  return (
    <main className="workspace">
      <AdminCatalogFilter query={q} />
      <TorrentAdminPanel torrents={page.items} />
      <PaginationLinks page={page.page} pageCount={page.pageCount} pathname="/admin/torrents" query={q ? { q } : {}} />
    </main>
  );
}
