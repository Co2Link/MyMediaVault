"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import type { PreviewRead } from "@/lib/types";

type PreviewImage = {
  alt: string;
  height: number;
  src: string;
  width: number;
};

export function VideoPreviewCarousel({
  preview,
  videoId,
}: {
  preview: PreviewRead;
  videoId: string;
}) {
  const images = useMemo(() => previewImages(videoId, preview), [preview, videoId]);
  const [currentIndex, setCurrentIndex] = useState(0);

  if (images.length === 0) {
    return (
      <div className={`video-preview-empty preview-${preview.status}`}>
        <span>{preview.status === "processing" ? "Generating preview" : "No preview available"}</span>
      </div>
    );
  }

  const current = images[Math.min(currentIndex, images.length - 1)];

  return (
    <div className="video-preview-carousel">
      <Image
        alt={current.alt}
        className="video-preview-image"
        height={current.height}
        src={current.src}
        unoptimized
        width={current.width}
      />
      {images.length > 1 ? (
        <div className="preview-controls" aria-label="Preview frame controls">
          <button
            aria-label="Previous preview image"
            className="preview-arrow"
            onClick={() => setCurrentIndex((index) => (index === 0 ? images.length - 1 : index - 1))}
            type="button"
          >
            &lt;
          </button>
          <span className="preview-counter">
            {currentIndex + 1}/{images.length}
          </span>
          <button
            aria-label="Next preview image"
            className="preview-arrow"
            onClick={() => setCurrentIndex((index) => (index + 1) % images.length)}
            type="button"
          >
            &gt;
          </button>
        </div>
      ) : null}
    </div>
  );
}

function previewImages(videoId: string, preview: PreviewRead): PreviewImage[] {
  const images: PreviewImage[] = [];
  if (preview.sheet) {
    images.push({
      alt: "Torrent preview sheet",
      height: preview.sheet.height,
      src: `/api/videos/${videoId}/preview/sheet`,
      width: preview.sheet.width,
    });
  }

  for (const [index, frame] of preview.frames.entries()) {
    images.push({
      alt: `Torrent preview frame ${index + 1}`,
      height: frame.height,
      src: `/api/videos/${videoId}/preview/frame-${index}`,
      width: frame.width,
    });
  }

  return images;
}
