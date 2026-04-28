import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderApp } from "../../test/render";
import { CollectionPage } from "./CollectionPage";

describe("CollectionPage", () => {
  it("renders search results", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          items: [
            {
              id: "00000000-0000-0000-0000-000000000001",
              displayTitle: "Ocean Film",
              title: "Ocean Film",
              rating: 4,
              infoHash: "0123456789abcdef0123456789abcdef01234567",
              torrentName: "Ocean Torrent",
              metadataStatus: "succeeded",
              tags: [{ id: "00000000-0000-0000-0000-000000000002", name: "Drama" }],
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            },
          ],
          total: 1,
          limit: 25,
          offset: 0,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    renderApp(<CollectionPage />);
    expect(await screen.findByText("Ocean Film")).toBeInTheDocument();
    expect(screen.getByText("Drama")).toBeInTheDocument();
  });

  it("renders empty state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [], total: 0, limit: 25, offset: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    renderApp(<CollectionPage />);
    expect(await screen.findByText(/no videos match/i)).toBeInTheDocument();
  });
});
