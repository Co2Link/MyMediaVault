import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { VideoPreviewGallery } from "@/components/video-preview-gallery";
import type { PreviewRead } from "@/lib/types";

const preview: PreviewRead = {
  status: "complete",
  phase: null,
  failureCount: 0,
  lastOutcome: "completed",
  lastError: null,
  queuedAt: null,
  updatedAt: "2024-01-01T00:00:00.000Z",
  sheet: {
    key: "previews/sheet.jpg",
    width: 1200,
    height: 800,
    mimeType: "image/jpeg",
  },
  frames: [
    {
      key: "previews/frame-1.jpg",
      width: 640,
      height: 360,
      timestampSeconds: 1,
    },
    {
      key: "previews/frame-2.jpg",
      width: 640,
      height: 360,
      timestampSeconds: 2,
    },
  ],
  diagnostics: {
    artifactVersion: "1.2.0",
    artifactFingerprint: "fingerprint",
    statusReason: null,
    downloadedBytes: null,
    elapsedSeconds: null,
    selectedFilePath: null,
    selectedFileSizeBytes: null,
    warnings: [],
    details: {},
  },
};

describe("VideoPreviewGallery", () => {
  it("can render collapsed by default", async () => {
    const user = userEvent.setup();
    const { container, getByText } = render(<VideoPreviewGallery defaultOpen={false} preview={preview} videoId="video-1" />);

    expect(container.querySelector("details")?.open).toBe(false);

    await user.click(getByText("Torrent preview"));

    expect(container.querySelector("details")?.open).toBe(true);
  });

  it("treats the sheet as a gallery image and opens full size navigation", async () => {
    const user = userEvent.setup();
    const { findByRole, getAllByRole, getByRole, getByText } = render(
      <VideoPreviewGallery preview={preview} videoId="video-1" />,
    );

    expect(getAllByRole("img")).toHaveLength(3);

    await user.click(getByRole("button", { name: "Open torrent preview sheet" }));

    expect(await findByRole("dialog", { name: "Full size preview image" })).toBeVisible();
    expect(getByText("1/3")).toBeVisible();

    await user.click(getByRole("button", { name: "Next preview image" }));
    expect(getByText("2/3")).toBeVisible();
  });
});
