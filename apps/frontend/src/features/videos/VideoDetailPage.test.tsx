import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderApp } from "../../test/render";
import { VideoDetailPage } from "./VideoDetailPage";

const baseVideo = {
  id: "00000000-0000-0000-0000-000000000001",
  displayTitle: "Original",
  title: "Original",
  description: "Original description",
  rating: 3,
  infoHash: "0123456789abcdef0123456789abcdef01234567",
  torrentName: "Fixture Torrent",
  metadataStatus: "succeeded",
  metadataError: null,
  tags: [],
  files: [{ path: "Fixture/movie.mp4", sizeBytes: 250 }],
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
};

describe("VideoDetailPage", () => {
  it("saves user-specific video details", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify(baseVideo), { status: 200, headers: { "Content-Type": "application/json" } }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...baseVideo, title: "Updated", rating: 5 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    renderApp(<VideoDetailPage videoId={baseVideo.id} />);

    const title = await screen.findByLabelText(/title/i);
    await userEvent.clear(title);
    await userEvent.type(title, "Updated");
    await userEvent.selectOptions(screen.getByLabelText(/rating/i), "5");
    await userEvent.click(screen.getByRole("button", { name: /save details/i }));

    expect(await screen.findByText(/video details saved/i)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(
      `http://localhost:8000/videos/${baseVideo.id}`,
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ title: "Updated", description: "Original description", rating: 5 }),
      }),
    );
  });
});
