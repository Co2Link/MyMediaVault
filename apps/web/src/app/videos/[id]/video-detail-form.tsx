"use client";

import { useActionState } from "react";
import type { ActorRead, TagRead, VideoDetail } from "@/lib/types";
import { deleteVideoAction, updateVideoAction } from "@/app/videos/[id]/actions";
import { VideoActorPicker } from "@/components/video-actor-picker";
import { VideoTagPicker } from "@/components/video-tag-picker";

export function VideoDetailForm({
  actors,
  tags,
  video,
}: {
  actors: ActorRead[];
  tags: TagRead[];
  video: VideoDetail;
}) {
  const boundAction = updateVideoAction.bind(null, video.id);
  const [state, action, pending] = useActionState(boundAction, {
    error: null,
    success: null,
  });
  const deleteBoundAction = deleteVideoAction.bind(null, video.id);
  const [deleteState, deleteAction, deletePending] = useActionState(deleteBoundAction, { error: null });

  return (
    <div className="form-grid">
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
        <VideoActorPicker
          actors={actors}
          detectedActors={video.systemActors}
          selectedActorIds={video.userActors.map((actor) => actor.id)}
        />
        <VideoTagPicker tags={tags} selectedTagIds={video.tags.map((tag) => tag.id)} />
        {state.error ? <p className="error-copy">{state.error}</p> : null}
        {state.success ? <p className="success-copy">{state.success}</p> : null}
        <button className="primary-button" disabled={pending} type="submit">
          {pending ? "Saving" : "Save details"}
        </button>
      </form>
      <div className="form-grid">
        {deleteState.error ? <p className="error-copy">{deleteState.error}</p> : null}
        <form action={deleteAction}>
          <button className="ghost-button danger-button" disabled={deletePending} type="submit">
            {deletePending ? "Deleting" : "Delete video"}
          </button>
        </form>
      </div>
    </div>
  );
}
