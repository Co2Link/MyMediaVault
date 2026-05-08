import { expect, test } from "@playwright/test";

test("normal users see restricted tag management state", async ({ page }) => {
  await page.goto("/admin/tags");
  await expect(page.getByText("Administrator access is required.")).toBeVisible();
});
