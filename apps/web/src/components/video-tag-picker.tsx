"use client";

import type { TagRead } from "@/lib/types";

export function VideoTagPicker({
  tags,
  selectedTagIds = [],
}: {
  tags: TagRead[];
  selectedTagIds?: string[];
}) {
  const selected = new Set(selectedTagIds);

  return (
    <fieldset className="tag-picker">
      <legend>Tags</legend>
      <p className="muted-copy">Choose from existing tags. Tag names are managed in Admin.</p>
      {tags.length === 0 ? (
        <p className="muted-copy">No tags exist yet. Create one in Admin to attach it to videos.</p>
      ) : (
        <div className="tag-picker-grid">
          {tags.map((tag) => (
            <label className="tag-option" key={tag.id}>
              <input defaultChecked={selected.has(tag.id)} name="tagIds" type="checkbox" value={tag.id} />
              <span>{tag.name}</span>
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}
