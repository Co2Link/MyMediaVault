"use client";

import Image from "next/image";
import type { ActorRead } from "@/lib/types";

export function VideoActorPicker({
  actors,
  selectedActorIds = [],
}: {
  actors: ActorRead[];
  selectedActorIds?: string[];
}) {
  const selected = new Set(selectedActorIds);

  return (
    <fieldset className="actor-picker">
      <legend>Actors</legend>
      {actors.length === 0 ? (
        <p className="muted-copy">No actors exist yet.</p>
      ) : (
        <div className="actor-picker-grid">
          {actors.map((actor) => (
            <label className="actor-option" key={actor.id}>
              <input
                aria-label={actor.name}
                defaultChecked={selected.has(actor.id)}
                name="actorIds"
                type="checkbox"
                value={actor.id}
              />
              <span aria-hidden="true" className="actor-option-image">
                {actor.hasProfileImage ? (
                  <Image
                    alt=""
                    fill
                    sizes="40px"
                    src={`/api/actors/${actor.id}/image?v=${encodeURIComponent(actor.updatedAt)}`}
                    unoptimized
                  />
                ) : (
                  <span>{actor.name.slice(0, 1).toUpperCase()}</span>
                )}
              </span>
              <span>{actor.name}</span>
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}
