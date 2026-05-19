import { expect, test } from "@playwright/test";

test("admin users can create, edit, view, and delete actors", async ({ page }) => {
  const actorName = `e2e-actor-${Date.now()}`;
  const updatedName = `${actorName}-updated`;

  await page.goto("/");
  await page.getByRole("link", { name: "Actors" }).click();
  await expect(page.getByRole("heading", { name: "Actor management" })).toBeVisible();

  await page.getByLabel("Name").first().fill(actorName);
  await page.getByLabel("Description").first().fill("E2E actor profile");
  await page.getByLabel("Profile image").first().setInputFiles({
    name: "profile.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
      "base64",
    ),
  });
  await page.getByRole("button", { name: "Create actor" }).click();

  const actorItem = page.locator("li").filter({ has: page.locator(`input[value="${actorName}"]`) });
  await expect(actorItem).toBeVisible();
  await expect(actorItem.getByRole("img", { name: `${actorName} profile image` })).toBeVisible();

  await actorItem.getByLabel("Name").fill(updatedName);
  await actorItem.getByRole("button", { name: "Save" }).click();

  const updatedItem = page.locator("li").filter({ has: page.locator(`input[value="${updatedName}"]`) });
  await expect(updatedItem).toBeVisible();
  await expect(updatedItem.getByRole("img", { name: `${updatedName} profile image` })).toBeVisible();

  await updatedItem.getByRole("link", { name: "View profile" }).click();
  await expect(page.getByRole("heading", { name: updatedName })).toBeVisible();
  await expect(page.getByText("E2E actor profile")).toBeVisible();
  await expect(page.getByRole("img", { name: `${updatedName} profile image` })).toBeVisible();

  await page.getByRole("link", { name: "Actors" }).click();
  await expect(updatedItem).toBeVisible();
  await updatedItem.getByRole("button", { name: "Delete" }).click();
  await expect(updatedItem).toHaveCount(0);
});
