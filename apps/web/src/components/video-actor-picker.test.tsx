import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VideoActorPicker } from "@/components/video-actor-picker";

describe("VideoActorPicker", () => {
  it("shows available actors and selected state", () => {
    const { getByLabelText, getByText } = render(
      <VideoActorPicker
        selectedActorIds={["actor-2"]}
        actors={[
          {
            id: "actor-1",
            name: "Jane Actor",
            description: null,
            hasProfileImage: false,
            createdAt: "2024-01-01T00:00:00.000Z",
            updatedAt: "2024-01-01T00:00:00.000Z",
          },
          {
            id: "actor-2",
            name: "Sam Actor",
            description: "Lead",
            hasProfileImage: false,
            createdAt: "2024-01-01T00:00:00.000Z",
            updatedAt: "2024-01-01T00:00:00.000Z",
          },
        ]}
      />,
    );

    expect(getByText("Actors")).toBeVisible();
    expect(getByLabelText("Jane Actor")).not.toBeChecked();
    expect(getByLabelText("Sam Actor")).toBeChecked();
  });
});
