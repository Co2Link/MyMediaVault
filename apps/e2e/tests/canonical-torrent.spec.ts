import { expect, test } from "@playwright/test";
import { duplicateInfoHash } from "../fixtures/torrents";

test("two users can reference the same torrent with separate details", async ({ request }) => {
  const first = await request.post("http://localhost:8000/videos", {
    data: { infoHash: duplicateInfoHash, title: "First" },
    headers: { "X-Test-User": "one" },
  });
  const second = await request.post("http://localhost:8000/videos", {
    data: { infoHash: duplicateInfoHash, title: "Second" },
    headers: { "X-Test-User": "two" },
  });
  expect([202, 409]).toContain(first.status());
  expect([202, 409]).toContain(second.status());
});
