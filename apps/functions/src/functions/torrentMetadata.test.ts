import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  timer: vi.fn(),
}));

vi.mock("@azure/functions", () => ({
  app: {
    timer: mocks.timer,
  },
}));

describe("torrent metadata function registration", () => {
  it("registers the timer trigger", async () => {
    await import("./torrentMetadata.js");

    expect(mocks.timer).toHaveBeenCalledWith(
      "processTorrentMetadata",
      expect.objectContaining({
        schedule: "0 * * * * *",
      }),
    );
  });
});
