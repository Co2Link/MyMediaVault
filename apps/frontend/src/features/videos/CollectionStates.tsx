export function LoadingState() {
  return <p role="status">Loading collection</p>;
}

export function ErrorState({ message }: { message: string }) {
  return <p className="error">{message}</p>;
}

export function EmptyState() {
  return <p className="empty">No videos match this search.</p>;
}
