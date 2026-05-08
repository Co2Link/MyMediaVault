import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { connectMongo, TagModel, disconnectMongo } from "@mymediavault/core/db";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const adminStorageState = path.join(dirname, "..", ".auth", "admin.json");

test.afterAll(async () => {
  await disconnectMongo();
});

test("user can assign and edit video tags", async ({ browser, page }) => {
  const adminContext = await browser.newContext({ storageState: adminStorageState });
  const adminPage = await adminContext.newPage();
  const tagName = `e2e-tag-${Date.now().toString(16)}`;
  const infoHash = `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa${Date.now().toString(16).padStart(8, "0").slice(-8)}`;
  const title = `Tagged Video ${Date.now()}`;

  await adminPage.goto("/admin/tags");
  await adminPage.getByLabel("Tag name").fill(tagName);
  await adminPage.getByRole("button", { name: "Create tag" }).click();

  await connectMongo();
  await expect
    .poll(async () => (await TagModel.findOne({ name: tagName }).lean().exec()) !== null)
    .toBe(true);

  await adminContext.close();

  await page.goto("/add");
  await page.getByLabel("Info hash").fill(infoHash);
  await page.getByLabel("Title").fill(title);
  await expect(page.getByLabel(tagName)).toBeVisible();
  await page.getByLabel(tagName).check();
  await page.getByRole("button", { name: "Add video" }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByLabel(tagName)).toBeChecked();

  await page.getByLabel(tagName).uncheck();
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(page.getByText("Video details saved.")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel(tagName)).not.toBeChecked();
});
