import Link from "next/link";
import { ActorLinks } from "@/components/actor-links";
import { MetadataStatusBadge } from "@/components/metadata-status";
import { TagLinks } from "@/components/tag-links";
import { VideoPreviewCarousel } from "@/components/video-preview-carousel";
import type { VideoSummary } from "@/lib/types";

export function VideoCard({ video }: { video: VideoSummary }) {
  return (
    <article className="video-card">
      <VideoPreviewCarousel preview={video.preview} videoId={video.id} />
      <div className="video-card-header">
        <div>
          <h2>{video.displayTitle ?? video.infoHash}</h2>
          <p className="muted-copy">{video.torrentName ?? video.infoHash}</p>
        </div>
        <MetadataStatusBadge status={video.processingState} />
      </div>
      <dl className="meta-grid">
        <div>
          <dt>Rating</dt>
          <dd>{video.rating ?? "Unrated"}</dd>
        </div>
        <div>
          <dt>Actors</dt>
          <dd>
            <ActorLinks actors={video.actors} />
          </dd>
        </div>
        <div>
          <dt>Tags</dt>
          <dd>
            <TagLinks tags={video.tags} />
          </dd>
        </div>
      </dl>
      <Link className="secondary-link" href={`/videos/${video.id}`}>
        View details
      </Link>
    </article>
  );
}
