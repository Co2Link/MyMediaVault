"use client";

import Image from "next/image";
import Link from "next/link";
import { useActionState } from "react";
import { createActorAction, deleteActorAction, updateActorAction } from "@/app/admin/actors/actions";
import type { ActorRead } from "@/lib/types";

export function ActorAdminPanel({ actors }: { actors: ActorRead[] }) {
  const [state, createAction, pending] = useActionState(createActorAction, { error: null });

  return (
    <section className="editor-card form-grid">
      <div>
        <p className="eyebrow">Admin</p>
        <h1>Actor management</h1>
      </div>
      <form action={createAction} className="actor-admin-create">
        <label>
          Name
          <input name="name" required />
        </label>
        <label>
          Description
          <textarea name="description" rows={3} />
        </label>
        <label>
          Profile image
          <input accept="image/jpeg,image/png,image/webp,image/gif" name="profileImage" required type="file" />
        </label>
        {state.error ? <p className="error-copy">{state.error}</p> : null}
        <button className="primary-button" disabled={pending} type="submit">
          {pending ? "Creating" : "Create actor"}
        </button>
      </form>
      <ul className="actor-admin-list">
        {actors.map((actor) => (
          <li key={actor.id}>
            <div className="actor-admin-image">
              {actor.hasProfileImage ? (
                <Image
                  alt={`${actor.name} profile image`}
                  fill
                  sizes="96px"
                  src={`/api/actors/${actor.id}/image?v=${encodeURIComponent(actor.updatedAt)}`}
                  unoptimized
                />
              ) : (
                <span>{actor.name.slice(0, 1).toUpperCase()}</span>
              )}
            </div>
            {actor.profileImageSource === "system" ? (
              <p className="muted-copy">
                System profile score: {actor.profileImageScore?.toFixed(2) ?? "legacy"}
                {actor.profileImageFlags.length > 0 ? ` · ${actor.profileImageFlags.join(" · ")}` : ""}
              </p>
            ) : null}
            <form action={updateActorAction.bind(null, actor.id)} className="actor-admin-edit">
              <label>
                Name
                <input defaultValue={actor.name} name="name" required />
              </label>
              <label>
                Description
                <textarea defaultValue={actor.description ?? ""} name="description" rows={3} />
              </label>
              <label>
                Replace profile image
                <input accept="image/jpeg,image/png,image/webp,image/gif" name="profileImage" type="file" />
              </label>
              <div className="actor-admin-actions">
                <Link className="secondary-link" href={`/actors/${actor.id}`}>
                  View profile
                </Link>
                <button className="ghost-button" type="submit">
                  Save
                </button>
              </div>
            </form>
            <form action={deleteActorAction.bind(null, actor.id)}>
              <button className="ghost-button danger-button" type="submit">
                Delete
              </button>
            </form>
          </li>
        ))}
      </ul>
      {actors.length === 0 ? <p className="muted-copy">No actors have been created yet.</p> : null}
    </section>
  );
}
