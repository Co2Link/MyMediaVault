import Link from "next/link";
import type { ActorRead } from "@/lib/types";

export function ActorLinks({ actors }: { actors: ActorRead[] }) {
  if (actors.length === 0) {
    return <>None</>;
  }

  return (
    <span className="actor-link-list">
      {actors.map((actor, index) => (
        <span key={actor.id}>
          {index > 0 ? ", " : null}
          <Link href={`/actors/${actor.id}`}>{actor.name}</Link>
        </span>
      ))}
    </span>
  );
}
