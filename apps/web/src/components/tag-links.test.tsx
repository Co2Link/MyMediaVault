import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TagLinks } from "@/components/tag-links";

describe("TagLinks", () => {
  it("links each read-only tag to its result page", () => {
    render(
      <TagLinks
        tags={[
          { id: "tag-1", name: "Drama" },
          { id: "tag-2", name: "Favorites" },
        ]}
      />,
    );

    expect(screen.getByRole("link", { name: "Drama" })).toHaveAttribute("href", "/tags/tag-1");
    expect(screen.getByRole("link", { name: "Favorites" })).toHaveAttribute("href", "/tags/tag-2");
  });

  it("renders an empty value when no tags are assigned", () => {
    render(<TagLinks tags={[]} />);

    expect(screen.getByText("None")).toBeVisible();
  });
});
