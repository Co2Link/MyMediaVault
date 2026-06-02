import type { TorrentSummary } from "@/lib/types";
import {
  cancelTorrentProcessingAction,
  deleteTorrentAction,
  queueTorrentProcessingAction,
  reanalyzeTorrentActorsAction,
} from "@/app/admin/torrents/actions";
import { VideoPreviewGallery } from "@/components/video-preview-gallery";

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
                {torrent.videoCount} video{torrent.videoCount === 1 ? "" : "s"} · {torrent.processingState}
              </p>
              <VideoPreviewGallery
                artifactBasePath={`/api/admin/torrents/${torrent.id}/preview`}
                defaultOpen={false}
                preview={torrent.preview}
              />
              <details className="admin-diagnostics">
                <summary>Preview: {torrent.preview.status}</summary>
                <dl className="diagnostics-grid">
                  <DiagnosticTerm label="Phase" value={torrent.preview.phase} />
                  <DiagnosticTerm label="Failures" value={torrent.preview.failureCount} />
                  <DiagnosticTerm label="Last outcome" value={torrent.preview.lastOutcome} />
                  <DiagnosticTerm label="Last error" value={torrent.preview.lastError} />
                  <DiagnosticTerm label="Queued" value={formatDate(torrent.preview.queuedAt)} />
                  <DiagnosticTerm label="Updated" value={formatDate(torrent.preview.updatedAt)} />
                  <DiagnosticTerm label="Artifact version" value={torrent.preview.diagnostics.artifactVersion} />
                  <DiagnosticTerm label="Fingerprint" value={torrent.preview.diagnostics.artifactFingerprint} />
                  <DiagnosticTerm label="Status reason" value={torrent.preview.diagnostics.statusReason} />
                  <DiagnosticTerm label="Downloaded" value={formatBytes(torrent.preview.diagnostics.downloadedBytes)} />
                  <DiagnosticTerm label="Elapsed" value={formatSeconds(torrent.preview.diagnostics.elapsedSeconds)} />
                  <DiagnosticTerm label="Selected file" value={torrent.preview.diagnostics.selectedFilePath} />
                  <DiagnosticTerm label="Selected file size" value={formatBytes(torrent.preview.diagnostics.selectedFileSizeBytes)} />
                  <DiagnosticTerm label="Frames" value={torrent.preview.frames.length} />
                  <DiagnosticTerm label="Sheet" value={torrent.preview.sheet ? torrent.preview.sheet.key : null} />
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
              <details className="admin-diagnostics">
                <summary>Actor analysis: {torrent.actorAnalysis.status}</summary>
                <dl className="diagnostics-grid">
                  <DiagnosticTerm label="Attempts" value={torrent.actorAnalysis.attempts} />
                  <DiagnosticTerm label="Last attempt" value={formatDate(torrent.actorAnalysis.lastAttemptAt)} />
                  <DiagnosticTerm label="Updated" value={formatDate(torrent.actorAnalysis.updatedAt)} />
                  <DiagnosticTerm label="Fingerprint" value={torrent.actorAnalysis.fingerprint} />
                  <DiagnosticTerm label="Error" value={torrent.actorAnalysis.error} />
                </dl>
                {Object.keys(torrent.actorAnalysis.diagnostics).length > 0 ? (
                  <pre className="diagnostics-json">
                    {JSON.stringify(torrent.actorAnalysis.diagnostics, null, 2)}
                  </pre>
                ) : null}
              </details>
            </div>
            <div className="admin-actions">
              <form action={reanalyzeTorrentActorsAction.bind(null, torrent.id)}>
                <button className="ghost-button" type="submit">
                  Reanalyze actors
                </button>
              </form>
              <form action={queueTorrentProcessingAction.bind(null, torrent.id)}>
                <button className="ghost-button" type="submit">
                  Queue again
                </button>
              </form>
              <form action={cancelTorrentProcessingAction.bind(null, torrent.id)}>
                <button className="ghost-button" type="submit">
                  Cancel
                </button>
              </form>
              <form action={deleteTorrentAction.bind(null, torrent.id)}>
                <button className="ghost-button danger-button" type="submit">
                  Delete torrent
                </button>
              </form>
            </div>
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
