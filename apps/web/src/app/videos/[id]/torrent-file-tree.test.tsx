import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createFileTree, TorrentFileTree } from "@/app/videos/[id]/torrent-file-tree";

describe("TorrentFileTree", () => {
  it("renders folders collapsed by default", () => {
    const tree = createFileTree([
      { path: "folder/video-a.mp4", sizeBytes: 1024 },
      { path: "folder/video-b.mp4", sizeBytes: 2048 },
    ]);

    const { container, getByText } = render(<TorrentFileTree node={tree} />);

    expect(getByText("folder")).toBeVisible();
    expect(container.querySelector("details")?.open).toBe(false);
  });
});
