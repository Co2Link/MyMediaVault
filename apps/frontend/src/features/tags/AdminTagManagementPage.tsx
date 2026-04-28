import { FormEvent, useEffect, useState } from "react";
import { createTag, deleteTag, listTags, updateTag, type Tag } from "./api";

export function AdminTagManagementPage() {
  const [tags, setTags] = useState<Tag[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setTags(await listTags());
  }

  useEffect(() => {
    load().catch((exc) => setError(exc instanceof Error ? exc.message : "Unable to load tags"));
  }, []);

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      await createTag(name);
      setName("");
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to create tag");
    }
  }

  async function onRename(tag: Tag) {
    const next = window.prompt("Rename tag", tag.name);
    if (!next) return;
    await updateTag(tag.id, next);
    await load();
  }

  async function onDelete(tag: Tag) {
    await deleteTag(tag.id);
    await load();
  }

  return (
    <section className="stack">
      <h2>Tags</h2>
      <form onSubmit={onCreate}>
        <label>
          Tag name
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <button className="primary-button" type="submit">Create tag</button>
      </form>
      {error ? <p className="error">{error}</p> : null}
      <ul>
        {tags.map((tag) => (
          <li key={tag.id}>
            {tag.name}
            <button type="button" onClick={() => void onRename(tag)}>Rename</button>
            <button type="button" onClick={() => void onDelete(tag)}>Delete</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
