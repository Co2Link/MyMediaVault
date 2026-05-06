import Link from "next/link";
import { MetadataStatusBadge } from "@/components/metadata-status";
import type { VideoSummary } from "@/lib/types";

export function VideoCard({ video }: { video: VideoSummary }) {
  return (
    <article className="video-card">
      <div className="video-card-header">
        <div>
          <h2>{video.displayTitle ?? video.infoHash}</h2>
          <p className="muted-copy">{video.torrentName ?? video.infoHash}</p>
        </div>
        <MetadataStatusBadge status={video.metadataStatus} />
      </div>
      <dl className="meta-grid">
        <div>
          <dt>Rating</dt>
          <dd>{video.rating ?? "Unrated"}</dd>
        </div>
        <div>
          <dt>Tags</dt>
          <dd>{video.tags.length ? video.tags.map((tag) => tag.name).join(", ") : "None"}</dd>
        </div>
      </dl>
      <Link className="secondary-link" href={`/videos/${video.id}`}>
        View details
      </Link>
    </article>
  );
}
