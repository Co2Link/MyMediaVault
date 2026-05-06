import { expect, test } from "@playwright/test";

test("admin users can create and delete tags", async ({ page }) => {
  const tagName = `e2e-tag-${Date.now()}`;

  await page.goto("/");
  await page.getByRole("link", { name: "Tags" }).click();
  await expect(page.getByRole("heading", { name: "Tag management" })).toBeVisible();

  await page.getByLabel("Tag name").fill(tagName);
  await page.getByRole("button", { name: "Create tag" }).click();

  const tagItem = page.locator("li").filter({ has: page.locator(`input[value="${tagName}"]`) });
  await expect(tagItem).toBeVisible();

  await tagItem.getByRole("button", { name: "Delete" }).click();
  await expect(tagItem).toHaveCount(0);
});
