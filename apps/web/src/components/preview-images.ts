import type { PreviewRead } from "@/lib/types";

export type PreviewImage = {
  alt: string;
  height: number;
  src: string;
  width: number;
};

export function previewImages(basePath: string, preview: PreviewRead): PreviewImage[] {
  const images: PreviewImage[] = [];
  if (preview.sheet) {
    images.push({
      alt: "Torrent preview sheet",
      height: preview.sheet.height,
      src: `${basePath}/sheet`,
      width: preview.sheet.width,
    });
  }

  for (const [index, frame] of preview.frames.entries()) {
    images.push({
      alt: `Torrent preview frame ${index + 1}`,
      height: frame.height,
      src: `${basePath}/frame-${index}`,
      width: frame.width,
    });
  }

  return images;
}
