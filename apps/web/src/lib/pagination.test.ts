import { describe, expect, it } from "vitest";
import { firstQueryValue, paginate } from "@/lib/pagination";

describe("pagination", () => {
  it("returns the requested bounded slice", () => {
    expect(paginate(["a", "b", "c", "d", "e"], "2", 2)).toEqual({
      items: ["c", "d"],
      page: 2,
      pageCount: 3,
      totalItems: 5,
    });
  });

  it("clamps invalid and out-of-range pages", () => {
    expect(paginate(["a"], "invalid", 2).page).toBe(1);
    expect(paginate(["a"], "99", 2).page).toBe(1);
  });

  it("uses the first repeated query value", () => {
    expect(firstQueryValue(["first", "second"])).toBe("first");
  });
});
