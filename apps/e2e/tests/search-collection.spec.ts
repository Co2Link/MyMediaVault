import { expect, test } from "@playwright/test";

test("user can search collection", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your media vault" })).toBeVisible();
  await page.getByLabel("Search videos").fill("Fixture");
  await page.getByRole("button", { name: "Search" }).click();
});
