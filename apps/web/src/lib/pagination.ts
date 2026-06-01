export type PageSlice<T> = {
  items: T[];
  page: number;
  pageCount: number;
  totalItems: number;
};

export function paginate<T>(items: T[], requestedPage: string | undefined, pageSize: number): PageSlice<T> {
  const parsedPage = Number.parseInt(requestedPage ?? "1", 10);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const page = Number.isFinite(parsedPage) ? Math.min(Math.max(parsedPage, 1), pageCount) : 1;
  const start = (page - 1) * pageSize;

  return {
    items: items.slice(start, start + pageSize),
    page,
    pageCount,
    totalItems: items.length,
  };
}

export function firstQueryValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}
