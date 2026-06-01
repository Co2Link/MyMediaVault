import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { HeaderActions } from "@/components/header-actions";

describe("HeaderActions", () => {
  it("toggles the mobile navigation menu", async () => {
    const user = userEvent.setup();
    render(
      <HeaderActions
        email="user@example.com"
        image={null}
        isAdmin
        logoutAction={vi.fn()}
        name="User"
      />,
    );

    const button = screen.getByRole("button", { name: "Open navigation menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);

    expect(screen.getByRole("button", { name: "Close navigation menu" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: "Primary" })).toHaveClass("primary-nav-open");
  });
});
