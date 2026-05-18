import type { TorrentSummary } from "@/lib/types";
import { deleteTorrentAction } from "@/app/admin/torrents/actions";

export function TorrentAdminPanel({
  torrents,
}: {
  torrents: TorrentSummary[];
}) {
  return (
    <section className="editor-card">
      <div>
        <p className="eyebrow">Admin</p>
        <h1>Torrent management</h1>
      </div>
      <ul className="tag-list">
        {torrents.map((torrent) => (
          <li key={torrent.id}>
            <div>
              <strong>{torrent.name ?? torrent.infoHash}</strong>
              <p className="muted-copy">{torrent.infoHash}</p>
              <p className="muted-copy">
                {torrent.videoCount} video{torrent.videoCount === 1 ? "" : "s"} · {torrent.metadataStatus}
              </p>
              <details className="admin-diagnostics">
                <summary>Preview: {torrent.preview.status}</summary>
                <dl className="diagnostics-grid">
                  <DiagnosticTerm label="Attempts" value={torrent.preview.attempts} />
                  <DiagnosticTerm label="Last attempt" value={formatDate(torrent.preview.lastAttemptAt)} />
                  <DiagnosticTerm label="Updated" value={formatDate(torrent.preview.updatedAt)} />
                  <DiagnosticTerm label="Artifact version" value={torrent.preview.diagnostics.artifactVersion} />
                  <DiagnosticTerm label="Fingerprint" value={torrent.preview.diagnostics.artifactFingerprint} />
                  <DiagnosticTerm label="Downloaded" value={formatBytes(torrent.preview.diagnostics.downloadedBytes)} />
                  <DiagnosticTerm label="Elapsed" value={formatSeconds(torrent.preview.diagnostics.elapsedSeconds)} />
                  <DiagnosticTerm label="Engine attempts" value={torrent.preview.diagnostics.attempts} />
                  <DiagnosticTerm label="Strategy" value={torrent.preview.diagnostics.strategyName} />
                  <DiagnosticTerm label="Selected file" value={torrent.preview.diagnostics.selectedFilePath} />
                  <DiagnosticTerm label="Selected file size" value={formatBytes(torrent.preview.diagnostics.selectedFileSizeBytes)} />
                  <DiagnosticTerm label="Frames" value={torrent.preview.frames.length} />
                  <DiagnosticTerm label="Sheet" value={torrent.preview.sheet ? torrent.preview.sheet.key : null} />
                  <DiagnosticTerm label="Error" value={torrent.preview.error} />
                  <DiagnosticTerm label="Failure reason" value={torrent.preview.diagnostics.failureReason} />
                </dl>
                {torrent.preview.diagnostics.warnings.length > 0 ? (
                  <div className="diagnostics-block">
                    <strong>Warnings</strong>
                    <ul>
                      {torrent.preview.diagnostics.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {Object.keys(torrent.preview.diagnostics.details).length > 0 ? (
                  <pre className="diagnostics-json">
                    {JSON.stringify(torrent.preview.diagnostics.details, null, 2)}
                  </pre>
                ) : null}
              </details>
            </div>
            <form action={deleteTorrentAction.bind(null, torrent.id)}>
              <button className="ghost-button danger-button" type="submit">
                Delete torrent
              </button>
            </form>
          </li>
        ))}
      </ul>
      {torrents.length === 0 ? <p className="muted-copy">No torrents have been created yet.</p> : null}
    </section>
  );
}

function DiagnosticTerm({ label, value }: { label: string; value: number | string | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value ?? "None"}</dd>
    </div>
  );
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString("en-US") : null;
}

function formatSeconds(value: number | null) {
  return value === null ? null : `${value.toFixed(1)}s`;
}

function formatBytes(value: number | null) {
  if (value === null) {
    return null;
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
    style: "unit",
    unit: "byte",
    unitDisplay: "narrow",
  }).format(value);
}
