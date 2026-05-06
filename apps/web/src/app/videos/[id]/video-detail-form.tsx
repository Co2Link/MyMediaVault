"use client";

import { useActionState } from "react";
import type { VideoDetail } from "@/lib/types";
import { updateVideoAction } from "@/app/videos/[id]/actions";

export function VideoDetailForm({ video }: { video: VideoDetail }) {
  const boundAction = updateVideoAction.bind(null, video.id);
  const [state, action, pending] = useActionState(boundAction, {
    error: null,
    success: null,
  });

  return (
    <form action={action} className="form-grid">
      <label>
        Title
        <input defaultValue={video.title ?? ""} name="title" />
      </label>
      <label>
        Description
        <textarea defaultValue={video.description ?? ""} name="description" rows={6} />
      </label>
      <label>
        Rating
        <select defaultValue={video.rating?.toString() ?? ""} name="rating">
          <option value="">Unrated</option>
          {[1, 2, 3, 4, 5].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      {state.error ? <p className="error-copy">{state.error}</p> : null}
      {state.success ? <p className="success-copy">{state.success}</p> : null}
      <button className="primary-button" disabled={pending} type="submit">
        {pending ? "Saving" : "Save details"}
      </button>
    </form>
  );
}
