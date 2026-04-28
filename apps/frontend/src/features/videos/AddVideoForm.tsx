import { FormEvent, useState } from "react";
import { createVideo, type VideoDetail } from "./api";
import { MetadataStatus } from "./MetadataStatus";

export function AddVideoForm() {
  const [infoHash, setInfoHash] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [rating, setRating] = useState("");
  const [result, setResult] = useState<VideoDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const video = await createVideo({
        infoHash,
        title: title || undefined,
        description: description || undefined,
        rating: rating ? Number(rating) : undefined,
      });
      setResult(video);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to add video");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form-grid" onSubmit={onSubmit}>
      <h2>Add video</h2>
      <label>
        Info hash
        <input value={infoHash} onChange={(event) => setInfoHash(event.target.value)} required />
      </label>
      <label>
        Title
        <input value={title} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label>
        Description
        <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
      </label>
      <label>
        Rating
        <select value={rating} onChange={(event) => setRating(event.target.value)}>
          <option value="">Unrated</option>
          {[1, 2, 3, 4, 5].map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </select>
      </label>
      <button className="primary-button" type="submit" disabled={submitting}>
        {submitting ? "Adding" : "Add video"}
      </button>
      {error ? <p className="error">{error}</p> : null}
      {result ? <MetadataStatus status={result.metadataStatus} error={result.metadataError} /> : null}
    </form>
  );
}
