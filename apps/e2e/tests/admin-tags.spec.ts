import { expect, test } from "@playwright/test";

test("non-admin users see restricted tag management state", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Tags" }).click();
  await expect(page.getByText("Administrator access is required.")).toBeVisible();
});
