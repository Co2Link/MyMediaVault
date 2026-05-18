import Image from "next/image";
import type { PreviewRead } from "@/lib/types";

export function VideoPreviewGallery({
  preview,
  videoId,
}: {
  preview: PreviewRead;
  videoId: string;
}) {
  if (!preview.sheet && preview.frames.length === 0) {
    return (
      <section className={`preview-gallery preview-${preview.status}`}>
        <div>
          <h2>Torrent preview</h2>
          <p className="muted-copy">
            {preview.status === "processing"
              ? "Preview generation is running."
              : "Preview images are not available yet."}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className={`preview-gallery preview-${preview.status}`}>
      <div className="preview-gallery-header">
        <div>
          <h2>Torrent preview</h2>
          {preview.status === "partial" || preview.status === "failed" ? (
            <p className="error-copy">Preview generation degraded or failed.</p>
          ) : null}
        </div>
      </div>
      {preview.sheet ? (
        <Image
          alt="Torrent preview sheet"
          className="preview-sheet"
          height={preview.sheet.height}
          src={`/api/videos/${videoId}/preview/sheet`}
          unoptimized
          width={preview.sheet.width}
        />
      ) : null}
      {preview.frames.length > 0 ? (
        <div className="preview-frame-grid">
          {preview.frames.slice(0, 9).map((frame, index) => (
            <Image
              alt={`Torrent preview frame ${index + 1}`}
              className="preview-frame"
              height={frame.height}
              key={frame.key}
              src={`/api/videos/${videoId}/preview/frame-${index}`}
              unoptimized
              width={frame.width}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}
