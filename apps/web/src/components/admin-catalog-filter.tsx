export function AdminCatalogFilter({ query }: { query: string }) {
  return (
    <form className="catalog-filter">
      <label>
        Filter catalog
        <input defaultValue={query} name="q" placeholder="Filter visible records" type="search" />
      </label>
      <button className="ghost-button" type="submit">
        Filter
      </button>
    </form>
  );
}
