"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import { previewImages } from "@/components/preview-images";
import { VideoPreviewLightbox } from "@/components/video-preview-lightbox";
import type { PreviewRead } from "@/lib/types";

export function VideoPreviewCarousel({
  preview,
  videoId,
}: {
  preview: PreviewRead;
  videoId: string;
}) {
  const images = useMemo(() => previewImages(videoId, preview), [preview, videoId]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);

  if (images.length === 0) {
    return (
      <div className={`video-preview-empty preview-${preview.status}`}>
        <span>{preview.status === "processing" ? "Generating preview" : "No preview available"}</span>
      </div>
    );
  }

  const current = images[Math.min(currentIndex, images.length - 1)];
  const showPrevious = () => setCurrentIndex((index) => (index === 0 ? images.length - 1 : index - 1));
  const showNext = () => setCurrentIndex((index) => (index + 1) % images.length);

  return (
    <div className="video-preview-carousel">
      <button
        aria-label="Open full size preview"
        className="preview-image-button"
        onClick={() => setIsLightboxOpen(true)}
        type="button"
      >
        <Image
          alt={current.alt}
          className="video-preview-image"
          height={current.height}
          src={current.src}
          unoptimized
          width={current.width}
        />
      </button>
      {images.length > 1 ? (
        <div className="preview-controls" aria-label="Preview frame controls">
          <button
            aria-label="Previous preview image"
            className="preview-arrow"
            onClick={showPrevious}
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
            onClick={showNext}
            type="button"
          >
            &gt;
          </button>
        </div>
      ) : null}
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
  );
}
