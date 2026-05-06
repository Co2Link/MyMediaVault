export function VideoSearchForm({ query }: { query: string }) {
  return (
    <form action="/" className="search-form">
      <label>
        Search videos
        <input defaultValue={query} name="q" placeholder="Title, description, torrent name, or info hash" />
      </label>
      <button className="ghost-button" type="submit">
        Search
      </button>
    </form>
  );
}
