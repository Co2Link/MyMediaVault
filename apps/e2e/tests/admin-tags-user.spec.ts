import { expect, test } from "@playwright/test";

test("normal users see restricted tag management state", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Tags" }).click();
  await expect(page.getByText("Administrator access is required.")).toBeVisible();
});
