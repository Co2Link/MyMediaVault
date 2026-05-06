import { describe, expect, it } from "vitest";
import { normalizeInfoHash, normalizeOptionalText, normalizeRating } from "@/lib/validation";

describe("validation helpers", () => {
  it("normalizes hexadecimal info hashes", () => {
    expect(normalizeInfoHash("ABCDEF0123456789ABCDEF0123456789ABCDEF01")).toBe(
      "abcdef0123456789abcdef0123456789abcdef01",
    );
  });

  it("rejects invalid info hashes", () => {
    expect(() => normalizeInfoHash("bad")).toThrow(/40-character hexadecimal/);
  });

  it("normalizes optional text and rating", () => {
    expect(normalizeOptionalText("  hello  ")).toBe("hello");
    expect(normalizeOptionalText("   ")).toBeNull();
    expect(normalizeRating(4)).toBe(4);
    expect(normalizeRating("")).toBeNull();
  });
});
