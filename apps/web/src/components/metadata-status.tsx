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
    <p className={`status-pill status-${status}`} role="status">
      {labelByStatus[status]}
      {status === "failed" && error ? `: ${error}` : ""}
    </p>
  );
}
