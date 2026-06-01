import Link from "next/link";
import type { TagRead } from "@/lib/types";

export function TagLinks({ tags }: { tags: TagRead[] }) {
  if (tags.length === 0) {
    return <>None</>;
  }

  return (
    <span className="tag-link-list">
      {tags.map((tag, index) => (
        <span key={tag.id}>
          {index > 0 ? ", " : null}
          <Link href={`/tags/${tag.id}`}>{tag.name}</Link>
        </span>
      ))}
    </span>
  );
}
