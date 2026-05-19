"use client";

import Image from "next/image";
import { useEffect } from "react";
import type { PreviewImage } from "@/components/preview-images";

export function VideoPreviewLightbox({
  currentIndex,
  images,
  onClose,
  onNext,
  onPrevious,
}: {
  currentIndex: number;
  images: PreviewImage[];
  onClose: () => void;
  onNext: () => void;
  onPrevious: () => void;
}) {
  const current = images[currentIndex];

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
      if (event.key === "ArrowLeft") {
        onPrevious();
      }
      if (event.key === "ArrowRight") {
        onNext();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, onNext, onPrevious]);

  if (!current) {
    return null;
  }

  return (
    <div aria-label="Full size preview image" aria-modal="true" className="preview-lightbox" role="dialog">
      <button aria-label="Dismiss full size preview" className="preview-lightbox-backdrop" onClick={onClose} type="button" />
      <div className="preview-lightbox-content">
        <button aria-label="Close full size preview" className="preview-lightbox-close" onClick={onClose} type="button">
          x
        </button>
        <div className="preview-lightbox-image">
          <Image alt={current.alt} fill sizes="100vw" src={current.src} unoptimized />
        </div>
        {images.length > 1 ? (
          <div className="preview-lightbox-controls" aria-label="Full size preview controls">
            <button aria-label="Previous preview image" className="preview-arrow" onClick={onPrevious} type="button">
              &lt;
            </button>
            <span className="preview-counter">
              {currentIndex + 1}/{images.length}
            </span>
            <button aria-label="Next preview image" className="preview-arrow" onClick={onNext} type="button">
              &gt;
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
