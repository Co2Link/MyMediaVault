import { render, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { VideoPreviewCarousel } from "@/components/video-preview-carousel";
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
  ],
  diagnostics: {
    artifactVersion: "preview-v5",
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

describe("VideoPreviewCarousel", () => {
  it("opens a centered full-size preview when the image is clicked", async () => {
    const user = userEvent.setup();
    const { findByRole, getByRole } = render(<VideoPreviewCarousel preview={preview} videoId="video-1" />);

    await user.click(getByRole("button", { name: "Open full size preview" }));

    const dialog = await findByRole("dialog", { name: "Full size preview image" });

    expect(dialog).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Next preview image" })).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Previous preview image" })).toBeVisible();
    expect(within(dialog).getByText("1/2")).toBeVisible();
  });
});
