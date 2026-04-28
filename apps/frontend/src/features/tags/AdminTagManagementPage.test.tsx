import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderApp } from "../../test/render";
import { AdminTagManagementPage } from "./AdminTagManagementPage";

describe("AdminTagManagementPage", () => {
  it("creates and displays tags", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "00000000-0000-0000-0000-000000000001", name: "Drama" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([{ id: "00000000-0000-0000-0000-000000000001", name: "Drama" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    renderApp(<AdminTagManagementPage />);
    await userEvent.type(screen.getByLabelText(/tag name/i), "Drama");
    await userEvent.click(screen.getByRole("button", { name: /create tag/i }));
    expect(await screen.findByText("Drama")).toBeInTheDocument();
  });
});
