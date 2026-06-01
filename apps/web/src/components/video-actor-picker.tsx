"use client";

import Image from "next/image";
import type { ActorRead } from "@/lib/types";

export function VideoActorPicker({
  actors,
  detectedActors = [],
  selectedActorIds = [],
}: {
  actors: ActorRead[];
  detectedActors?: ActorRead[];
  selectedActorIds?: string[];
}) {
  const selected = new Set(selectedActorIds);

  return (
    <>
      {detectedActors.length > 0 ? (
        <fieldset className="actor-picker">
          <legend>Detected actors</legend>
          <div className="actor-picker-grid">
            {detectedActors.map((actor) => (
              <div className="actor-option" key={actor.id}>
                <ActorImage actor={actor} />
                <span>{actor.name}</span>
              </div>
            ))}
          </div>
        </fieldset>
      ) : null}
      <fieldset className="actor-picker">
        <legend>Manual actors</legend>
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
                <ActorImage actor={actor} />
                <span>{actor.name}</span>
              </label>
            ))}
          </div>
        )}
      </fieldset>
    </>
  );
}

function ActorImage({ actor }: { actor: ActorRead }) {
  return (
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
  );
}
