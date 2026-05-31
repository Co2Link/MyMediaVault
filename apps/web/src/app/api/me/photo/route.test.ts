import { beforeEach, describe, expect, it, vi } from "vitest";
import { auth } from "@/auth";
import { getAccountAccessToken } from "@/lib/db";
import { GET } from "@/app/api/me/photo/route";

vi.mock("@/auth", () => ({
  auth: vi.fn(),
}));

vi.mock("@/lib/db", () => ({
  getAccountAccessToken: vi.fn(),
}));

const authMock = vi.mocked(auth);
const getAccountAccessTokenMock = vi.mocked(getAccountAccessToken);

describe("GET /api/me/photo", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authMock.mockReset();
    getAccountAccessTokenMock.mockReset();
  });

  it("rejects unauthenticated requests", async () => {
    authMock.mockResolvedValue(null);

    const response = await GET();

    expect(response.status).toBe(401);
  });

  it("returns an initial avatar when the account has no access token", async () => {
    authMock.mockResolvedValue({ user: { id: "user-id", name: "Morgan" } });
    getAccountAccessTokenMock.mockResolvedValue(null);

    const response = await GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/svg+xml; charset=utf-8");
    expect(await response.text()).toContain(">M</text>");
  });

  it("returns an initial avatar when Microsoft Graph fails", async () => {
    authMock.mockResolvedValue({ user: { id: "user-id", name: "Morgan" } });
    getAccountAccessTokenMock.mockResolvedValue("access-token");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("Unavailable", { status: 503 }));

    const response = await GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/svg+xml; charset=utf-8");
  });
});
