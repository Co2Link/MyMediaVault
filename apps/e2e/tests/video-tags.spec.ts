import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { ActorModel, connectMongo, TagModel, TorrentModel, disconnectMongo } from "@mymediavault/core/db";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const adminStorageState = path.join(dirname, "..", ".auth", "admin.json");

test.afterAll(async () => {
  await disconnectMongo();
});

test("user can assign and edit video tags and actors", async ({ browser, page }) => {
  const adminContext = await browser.newContext({ storageState: adminStorageState });
  const adminPage = await adminContext.newPage();
  const tagName = `e2e-tag-${Date.now().toString(16)}`;
  const actorName = `e2e-actor-${Date.now().toString(16)}`;
  const infoHash = `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa${Date.now().toString(16).padStart(8, "0").slice(-8)}`;
  const title = `Tagged Video ${Date.now()}`;

  await adminPage.goto("/admin/tags");
  await adminPage.getByLabel("Tag name").fill(tagName);
  await adminPage.getByRole("button", { name: "Create tag" }).click();

  await connectMongo();
  await expect
    .poll(async () => (await TagModel.findOne({ name: tagName }).lean().exec()) !== null)
    .toBe(true);

  await adminPage.goto("/admin/actors");
  await adminPage.getByLabel("Name").first().fill(actorName);
  await adminPage.getByLabel("Description").first().fill("Actor assigned by e2e.");
  await adminPage.getByLabel("Profile image").first().setInputFiles({
    name: "profile.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
      "base64",
    ),
  });
  await adminPage.getByRole("button", { name: "Create actor" }).click();

  await expect
    .poll(async () => (await ActorModel.findOne({ name: actorName }).lean().exec()) !== null)
    .toBe(true);

  await adminContext.close();

  await page.goto("/add");
  await page.getByLabel("Info hash").fill(infoHash);
  await page.getByLabel("Title").fill(title);
  await expect(page.getByLabel(actorName)).toBeVisible();
  await page.getByLabel(actorName).check();
  await expect(page.getByLabel(tagName)).toBeVisible();
  await page.getByLabel(tagName).check();
  await page.getByRole("button", { name: "Add video" }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByRole("link", { name: actorName })).toBeVisible();
  await expect(page.getByRole("link", { name: tagName })).toBeVisible();
  await expect(page.getByLabel(actorName)).toBeChecked();
  await expect(page.getByLabel(tagName)).toBeChecked();

  const actor = await ActorModel.findOne({ name: actorName }).lean().exec();
  if (!actor) {
    throw new Error("Expected actor fixture to exist.");
  }
  await TorrentModel.updateOne({ infoHash }, { $set: { systemActorIds: [actor._id] } }).exec();
  await page.reload();
  await expect(page.getByRole("group", { name: "Detected actors" }).getByText(actorName)).toBeVisible();

  await page.getByRole("link", { name: tagName }).click();
  await expect(page).toHaveURL(/\/tags\/[^/]+$/);
  await expect(page.getByRole("heading", { name: tagName })).toBeVisible();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();

  await page.getByRole("link", { name: actorName }).click();
  await expect(page).toHaveURL(/\/actors\/[^/]+$/);
  await expect(page.getByRole("heading", { name: actorName })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Videos featuring this actor" })).toBeVisible();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();

  await page.getByRole("link", { name: "Collection" }).click();
  await page.getByLabel("Search videos").fill(title);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name: tagName }).click();
  await expect(page).toHaveURL(/\/tags\/[^/]+$/);
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await page.getByRole("link", { name: "View details" }).click();

  await page.getByLabel(actorName).uncheck();
  await page.getByLabel(tagName).uncheck();
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(page.getByText("Video details saved.")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("group", { name: "Detected actors" }).getByText(actorName)).toBeVisible();
  await expect(page.getByLabel(actorName)).not.toBeChecked();
  await expect(page.getByLabel(tagName)).not.toBeChecked();
});
