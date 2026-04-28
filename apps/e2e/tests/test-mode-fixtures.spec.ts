import { expect, test } from "@playwright/test";
import { adminUser, secondUser, standardUser } from "../fixtures/test-users";
import { duplicateInfoHash, fixtureInfoHash, invalidInfoHash } from "../fixtures/torrents";

test("test fixtures expose deterministic users and torrents", () => {
  expect(standardUser.headers["X-Test-User"]).toBe("test-user-1");
  expect(secondUser.headers["X-Test-User"]).toBe("test-user-2");
  expect(adminUser.headers["X-Test-Admin"]).toBe("true");
  expect(fixtureInfoHash).toHaveLength(40);
  expect(duplicateInfoHash).toHaveLength(40);
  expect(invalidInfoHash).toContain("not");
});
