import type { PreviewRead } from "@/lib/types";

export type PreviewImage = {
  alt: string;
  height: number;
  src: string;
  width: number;
};

export function previewImages(videoId: string, preview: PreviewRead): PreviewImage[] {
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
