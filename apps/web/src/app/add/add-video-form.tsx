"use client";

import { useActionState } from "react";
import { addVideoAction } from "@/app/add/actions";

export function AddVideoForm() {
  const [state, action, pending] = useActionState(addVideoAction, { error: null });

  return (
    <form action={action} className="editor-card form-grid">
      <div>
        <p className="eyebrow">Ingest</p>
        <h1>Add video</h1>
      </div>
      <label>
        Info hash
        <input name="infoHash" required />
      </label>
      <label>
        Title
        <input name="title" />
      </label>
      <label>
        Description
        <textarea name="description" rows={5} />
      </label>
      <label>
        Rating
        <select name="rating" defaultValue="">
          <option value="">Unrated</option>
          {[1, 2, 3, 4, 5].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      {state.error ? <p className="error-copy">{state.error}</p> : null}
      <button className="primary-button" disabled={pending} type="submit">
        {pending ? "Adding" : "Add video"}
      </button>
    </form>
  );
}
