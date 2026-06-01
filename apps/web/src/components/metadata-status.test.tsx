import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetadataStatusBadge } from "@/components/metadata-status";

describe("MetadataStatusBadge", () => {
  it("renders the ready label", () => {
    const { getByRole } = render(<MetadataStatusBadge status="succeeded" />);
    expect(getByRole("status")).toHaveTextContent("Metadata ready");
  });

  it("renders errors for failed metadata", () => {
    const { getByRole, getByText } = render(<MetadataStatusBadge error="Resolver failure" status="failed" />);
    expect(getByRole("status")).toHaveTextContent("Metadata failed");
    expect(getByText("Resolver failure")).toHaveClass("metadata-error");
  });
});
