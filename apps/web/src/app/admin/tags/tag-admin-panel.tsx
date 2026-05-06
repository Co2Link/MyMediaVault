"use client";

import { useActionState } from "react";
import { createTagAction, deleteTagAction, renameTagAction } from "@/app/admin/tags/actions";

export function TagAdminPanel({
  tags,
}: {
  tags: Array<{ id: string; name: string }>;
}) {
  const [state, createAction, pending] = useActionState(createTagAction, { error: null });

  return (
    <section className="editor-card form-grid">
      <div>
        <p className="eyebrow">Admin</p>
        <h1>Tag management</h1>
      </div>
      <form action={createAction} className="inline-form">
        <label className="stretch-field">
          Tag name
          <input name="name" required />
        </label>
        <button className="primary-button" disabled={pending} type="submit">
          Create tag
        </button>
      </form>
      {state.error ? <p className="error-copy">{state.error}</p> : null}
      <ul className="tag-list">
        {tags.map((tag) => (
          <li key={tag.id}>
            <form action={renameTagAction.bind(null, tag.id)} className="inline-form stretch-form">
              <input defaultValue={tag.name} name="name" required />
              <button className="ghost-button" type="submit">
                Rename
              </button>
            </form>
            <form action={deleteTagAction.bind(null, tag.id)}>
              <button className="ghost-button danger-button" type="submit">
                Delete
              </button>
            </form>
          </li>
        ))}
      </ul>
    </section>
  );
}
