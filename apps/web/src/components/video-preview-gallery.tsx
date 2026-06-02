"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import { previewImages } from "@/components/preview-images";
import { VideoPreviewLightbox } from "@/components/video-preview-lightbox";
import type { PreviewRead } from "@/lib/types";

export function VideoPreviewGallery({
  artifactBasePath,
  defaultOpen = true,
  preview,
  videoId,
}: {
  artifactBasePath?: string;
  defaultOpen?: boolean;
  preview: PreviewRead;
  videoId?: string;
}) {
  const basePath = artifactBasePath ?? `/api/videos/${videoId}/preview`;
  const images = useMemo(() => previewImages(basePath, preview), [basePath, preview]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);

  if (images.length === 0) {
    return (
      <details className={`preview-gallery preview-${preview.status}`} open={defaultOpen}>
        <summary>Torrent preview</summary>
        <p className="muted-copy">
          {preview.status === "running" ? "Preview generation is running." : "Preview images are not available yet."}
        </p>
      </details>
    );
  }

  const showPrevious = () => setCurrentIndex((index) => (index === 0 ? images.length - 1 : index - 1));
  const showNext = () => setCurrentIndex((index) => (index + 1) % images.length);
  const openLightbox = (index: number) => {
    setCurrentIndex(index);
    setIsLightboxOpen(true);
  };

  return (
    <details className={`preview-gallery preview-${preview.status}`} open={defaultOpen}>
      <summary>Torrent preview</summary>
      <div className="preview-gallery-body">
        <div>
          {preview.status === "partial" || preview.status === "exhausted" ? (
            <p className="error-copy">Preview generation degraded or failed.</p>
          ) : null}
        </div>
        <div className="preview-frame-grid">
          {images.map((image, index) => (
            <button
              aria-label={`Open ${image.alt.toLowerCase()}`}
              className="preview-frame-button"
              key={image.src}
              onClick={() => openLightbox(index)}
              type="button"
            >
              <Image
                alt={image.alt}
                className="preview-frame"
                height={image.height}
                src={image.src}
                unoptimized
                width={image.width}
              />
            </button>
          ))}
        </div>
        {isLightboxOpen ? (
          <VideoPreviewLightbox
            currentIndex={currentIndex}
            images={images}
            onClose={() => setIsLightboxOpen(false)}
            onNext={showNext}
            onPrevious={showPrevious}
          />
        ) : null}
      </div>
    </details>
  );
}
