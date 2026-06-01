import type { MetadataStatus } from "@/lib/types";

const labelByStatus: Record<MetadataStatus, string> = {
  pending: "Metadata pending",
  processing: "Metadata processing",
  succeeded: "Metadata ready",
  failed: "Metadata failed",
};

export function MetadataStatusBadge({
  status,
  error,
}: {
  status: MetadataStatus;
  error?: string | null;
}) {
  return (
    <div className="metadata-status">
      <p className={`status-pill status-${status}`} role="status">
        {labelByStatus[status]}
      </p>
      {status === "failed" && error ? <p className="metadata-error">{error}</p> : null}
    </div>
  );
}
