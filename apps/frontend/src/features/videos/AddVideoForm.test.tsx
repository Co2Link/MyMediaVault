import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderApp } from "../../test/render";
import { AddVideoForm } from "./AddVideoForm";

describe("AddVideoForm", () => {
  it("renders required info hash and optional fields", () => {
    renderApp(<AddVideoForm />);
    expect(screen.getByLabelText(/info hash/i)).toBeRequired();
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/rating/i)).toBeInTheDocument();
  });

  it("shows metadata status after submission", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: "00000000-0000-0000-0000-000000000001",
          displayTitle: "Fixture",
          title: "Fixture",
          rating: null,
          infoHash: "0123456789abcdef0123456789abcdef01234567",
          torrentName: "Fixture",
          metadataStatus: "pending",
          metadataError: null,
          tags: [],
          files: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      ),
    );

    renderApp(<AddVideoForm />);
    await userEvent.type(screen.getByLabelText(/info hash/i), "0123456789abcdef0123456789abcdef01234567");
    await userEvent.click(screen.getByRole("button", { name: /add video/i }));

    expect(await screen.findByText(/metadata pending/i)).toBeInTheDocument();
  });
});
