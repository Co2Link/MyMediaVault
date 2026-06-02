import type { TorrentProcessingState } from "@/lib/types";

const labelByStatus: Record<TorrentProcessingState, string> = {
  queued: "Preview queued",
  running: "Preview processing",
  partial: "Preview improving",
  complete: "Preview ready",
  exhausted: "Preview needs attention",
  cancelled: "Preview cancelled",
};

export function MetadataStatusBadge({
  status,
  error,
}: {
  status: TorrentProcessingState;
  error?: string | null;
}) {
  return (
    <div className="metadata-status">
      <p className={`status-pill status-${status}`} role="status">
        {labelByStatus[status]}
      </p>
      {status === "exhausted" && error ? <p className="metadata-error">{error}</p> : null}
    </div>
  );
}
