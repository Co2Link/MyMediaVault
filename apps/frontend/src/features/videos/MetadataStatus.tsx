import type { MetadataStatus as Status } from "./api";

const labels: Record<Status, string> = {
  pending: "Metadata pending",
  processing: "Metadata processing",
  succeeded: "Metadata ready",
  failed: "Metadata failed",
};

export function MetadataStatus({ status, error }: { status: Status; error?: string | null }) {
  return (
    <div className="status" role="status">
      <strong>{labels[status]}</strong>
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
