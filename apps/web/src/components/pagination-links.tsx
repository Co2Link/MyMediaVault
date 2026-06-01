import Link from "next/link";

export function PaginationLinks({
  page,
  pageCount,
  pathname,
  query = {},
}: {
  page: number;
  pageCount: number;
  pathname: string;
  query?: Record<string, string>;
}) {
  if (pageCount <= 1) {
    return null;
  }

  return (
    <nav aria-label="Pagination" className="pagination-links">
      {page > 1 ? <Link href={{ pathname, query: { ...query, page: page - 1 } }}>Previous</Link> : <span />}
      <span>
        Page {page} of {pageCount}
      </span>
      {page < pageCount ? <Link href={{ pathname, query: { ...query, page: page + 1 } }}>Next</Link> : <span />}
    </nav>
  );
}
