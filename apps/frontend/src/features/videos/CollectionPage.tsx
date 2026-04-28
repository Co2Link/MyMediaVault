import { FormEvent, useEffect, useState } from "react";
import { searchVideos, type VideoSummary } from "./api";
import { EmptyState, ErrorState, LoadingState } from "./CollectionStates";
import { MetadataStatus } from "./MetadataStatus";

type CollectionPageProps = {
  onSelectVideo?: (videoId: string) => void;
};

export function CollectionPage({ onSelectVideo }: CollectionPageProps) {
  const [query, setQuery] = useState("");
  const [videos, setVideos] = useState<VideoSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load(q = query) {
    setLoading(true);
    setError(null);
    try {
      const response = await searchVideos({ q });
      setVideos(response.items);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load collection");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load("");
  }, []);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void load(query);
  }

  return (
    <section className="stack">
      <h2>Your collection</h2>
      <form onSubmit={onSubmit}>
        <label>
          Search videos
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
      </form>
      {loading ? <LoadingState /> : null}
      {error ? <ErrorState message={error} /> : null}
      {!loading && !error && videos.length === 0 ? <EmptyState /> : null}
      <div className="stack">
        {videos.map((video) => (
          <article key={video.id}>
            <h3>{video.displayTitle ?? video.infoHash}</h3>
            <p>{video.torrentName ?? video.infoHash}</p>
            <MetadataStatus status={video.metadataStatus} />
            <p>{video.tags.map((tag) => tag.name).join(", ")}</p>
            {onSelectVideo ? (
              <button type="button" onClick={() => onSelectVideo(video.id)}>
                View details
              </button>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
