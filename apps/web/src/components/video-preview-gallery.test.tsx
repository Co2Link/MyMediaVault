import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { VideoPreviewGallery } from "@/components/video-preview-gallery";
import type { PreviewRead } from "@/lib/types";

const preview: PreviewRead = {
  status: "succeeded",
  error: null,
  attempts: 1,
  lastAttemptAt: null,
  updatedAt: "2024-01-01T00:00:00.000Z",
  sheet: {
    key: "previews/sheet.jpg",
    width: 1200,
    height: 800,
    mimeType: "image/jpeg",
    metadata: {},
  },
  frames: [
    {
      key: "previews/frame-1.jpg",
      width: 640,
      height: 360,
      timestampSeconds: 1,
      score: 0.9,
      metadata: {},
    },
    {
      key: "previews/frame-2.jpg",
      width: 640,
      height: 360,
      timestampSeconds: 2,
      score: 0.8,
      metadata: {},
    },
  ],
  diagnostics: {
    artifactVersion: "1.2.0",
    artifactFingerprint: "fingerprint",
    downloadedBytes: null,
    elapsedSeconds: null,
    attempts: null,
    strategyName: null,
    selectedFilePath: null,
    selectedFileSizeBytes: null,
    failureReason: null,
    warnings: [],
    details: {},
  },
};

describe("VideoPreviewGallery", () => {
  it("treats the sheet as a gallery image and opens full size navigation", async () => {
    const user = userEvent.setup();
    const { getAllByRole, getByRole, getByText } = render(<VideoPreviewGallery preview={preview} videoId="video-1" />);

    expect(getAllByRole("img")).toHaveLength(3);

    await user.click(getByRole("button", { name: "Open torrent preview sheet" }));

    expect(getByRole("dialog", { name: "Full size preview image" })).toBeVisible();
    expect(getByText("1/3")).toBeVisible();

    await user.click(getByRole("button", { name: "Next preview image" }));
    expect(getByText("2/3")).toBeVisible();
  });
});
