import { useEffect, useState } from "react";
import { getVideo, type VideoDetail } from "./api";
import { ErrorState, LoadingState } from "./CollectionStates";
import { MetadataStatus } from "./MetadataStatus";

export function VideoDetailPage({ videoId }: { videoId: string }) {
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVideo(videoId).then(setVideo).catch((exc) => setError(exc instanceof Error ? exc.message : "Unable to load video"));
  }, [videoId]);

  if (error) return <ErrorState message={error} />;
  if (!video) return <LoadingState />;

  return (
    <article className="stack">
      <h2>{video.displayTitle ?? video.infoHash}</h2>
      <MetadataStatus status={video.metadataStatus} error={video.metadataError} />
      <p>{video.description}</p>
      <ul>
        {video.files.map((file) => (
          <li key={file.path}>{file.path} ({file.sizeBytes} bytes)</li>
        ))}
      </ul>
    </article>
  );
}
