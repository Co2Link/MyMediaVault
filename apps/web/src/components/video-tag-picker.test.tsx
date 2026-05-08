import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VideoTagPicker } from "@/components/video-tag-picker";

describe("VideoTagPicker", () => {
  it("shows available tags and selected state", () => {
    const { getByLabelText, getByText } = render(
      <VideoTagPicker
        selectedTagIds={["tag-2"]}
        tags={[
          { id: "tag-1", name: "Drama" },
          { id: "tag-2", name: "Favorites" },
        ]}
      />,
    );

    expect(getByText("Choose from existing tags. Tag names are managed in Admin.")).toBeVisible();
    expect(getByLabelText("Drama")).not.toBeChecked();
    expect(getByLabelText("Favorites")).toBeChecked();
  });
});
