import { FormEvent, useEffect, useState } from "react";
import { getVideo, updateVideo, type VideoDetail } from "./api";
import { ErrorState, LoadingState } from "./CollectionStates";
import { MetadataStatus } from "./MetadataStatus";

export function VideoDetailPage({ videoId }: { videoId: string }) {
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getVideo(videoId).then(setVideo).catch((exc) => setError(exc instanceof Error ? exc.message : "Unable to load video"));
  }, [videoId]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!video) return;
    const form = new FormData(event.currentTarget);
    setError(null);
    setSaveStatus(null);
    setSaving(true);
    try {
      const updated = await updateVideo(video.id, {
        title: stringValue(form, "title"),
        description: stringValue(form, "description"),
        rating: numberValue(form, "rating"),
      });
      setVideo(updated);
      setSaveStatus("Video details saved");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to save video");
    } finally {
      setSaving(false);
    }
  }

  if (error) return <ErrorState message={error} />;
  if (!video) return <LoadingState />;

  return (
    <article className="stack">
      <h2>{video.displayTitle ?? video.infoHash}</h2>
      <MetadataStatus status={video.metadataStatus} error={video.metadataError} />
      <form className="form-grid" onSubmit={onSubmit}>
        <label>
          Title
          <input name="title" defaultValue={video.title ?? ""} maxLength={300} />
        </label>
        <label>
          Description
          <textarea name="description" defaultValue={video.description ?? ""} maxLength={5000} />
        </label>
        <label>
          Rating
          <select name="rating" defaultValue={video.rating?.toString() ?? ""}>
            <option value="">Unrated</option>
            {[1, 2, 3, 4, 5].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "Saving" : "Save details"}
        </button>
        {saveStatus ? <p className="status">{saveStatus}</p> : null}
      </form>
      <ul>
        {video.files.map((file) => (
          <li key={file.path}>
            {file.path} ({file.sizeBytes} bytes)
          </li>
        ))}
      </ul>
    </article>
  );
}

function stringValue(form: FormData, name: string) {
  const value = form.get(name);
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function numberValue(form: FormData, name: string) {
  const value = form.get(name);
  return typeof value === "string" && value ? Number(value) : undefined;
}
