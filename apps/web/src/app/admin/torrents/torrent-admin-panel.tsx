import type { TorrentSummary } from "@/lib/types";
import { deleteTorrentAction } from "@/app/admin/torrents/actions";

export function TorrentAdminPanel({
  torrents,
}: {
  torrents: TorrentSummary[];
}) {
  return (
    <section className="editor-card">
      <div>
        <p className="eyebrow">Admin</p>
        <h1>Torrent management</h1>
      </div>
      <ul className="tag-list">
        {torrents.map((torrent) => (
          <li key={torrent.id}>
            <div>
              <strong>{torrent.name ?? torrent.infoHash}</strong>
              <p className="muted-copy">{torrent.infoHash}</p>
              <p className="muted-copy">
                {torrent.videoCount} video{torrent.videoCount === 1 ? "" : "s"} · {torrent.metadataStatus}
              </p>
            </div>
            <form action={deleteTorrentAction.bind(null, torrent.id)}>
              <button className="ghost-button danger-button" type="submit">
                Delete torrent
              </button>
            </form>
          </li>
        ))}
      </ul>
      {torrents.length === 0 ? <p className="muted-copy">No torrents have been created yet.</p> : null}
    </section>
  );
}
