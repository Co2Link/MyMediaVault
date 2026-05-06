import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetadataStatusBadge } from "@/components/metadata-status";

describe("MetadataStatusBadge", () => {
  it("renders the ready label", () => {
    render(<MetadataStatusBadge status="succeeded" />);
    expect(screen.getByRole("status")).toHaveTextContent("Metadata ready");
  });

  it("renders errors for failed metadata", () => {
    render(<MetadataStatusBadge error="Resolver failure" status="failed" />);
    expect(screen.getByRole("status")).toHaveTextContent("Resolver failure");
  });
});
