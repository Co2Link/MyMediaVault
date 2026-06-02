import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetadataStatusBadge } from "@/components/metadata-status";

describe("MetadataStatusBadge", () => {
  it("renders the ready label", () => {
    const { getByRole } = render(<MetadataStatusBadge status="complete" />);
    expect(getByRole("status")).toHaveTextContent("Preview ready");
  });

  it("renders errors for exhausted processing", () => {
    const { getByRole, getByText } = render(<MetadataStatusBadge error="Resolver failure" status="exhausted" />);
    expect(getByRole("status")).toHaveTextContent("Preview needs attention");
    expect(getByText("Resolver failure")).toHaveClass("metadata-error");
  });
});
