import { expect, test } from "@playwright/test";

test("authenticated user can inspect the header account menu and log out", async ({ page }) => {
  await page.goto("/");

  const primaryNav = page.getByRole("navigation", { name: "Primary" });
  await expect(primaryNav).toBeVisible();
  await expect(primaryNav.getByRole("link", { name: "Collection" })).toBeVisible();
  await expect(primaryNav.getByRole("link", { name: "Add video" })).toBeVisible();

  await page.setViewportSize({ width: 440, height: 956 });
  await expect(primaryNav).not.toBeVisible();
  await page.getByRole("button", { name: "Open navigation menu" }).click();
  await expect(primaryNav).toBeVisible();
  await page.getByRole("button", { name: "Close navigation menu" }).click();
  await expect(primaryNav).not.toBeVisible();

  const avatarButton = page.getByRole("button", { name: "Open user menu" });
  await expect(avatarButton).toBeVisible();

  const avatarImage = page.getByRole("img", { name: /profile photo/i });
  const avatarFallback = page.locator(".avatar-fallback");
  await expect
    .poll(async () => {
      if (await avatarImage.isVisible().catch(() => false)) {
        return "photo";
      }
      if (await avatarFallback.isVisible().catch(() => false)) {
        return "fallback";
      }
      return "missing";
    })
    .toMatch(/photo|fallback/);

  await avatarButton.click();

  const userMenu = page.getByRole("menu");
  await expect(userMenu).toBeVisible();
  await expect(userMenu.locator(".user-menu-copy strong")).toContainText(/\S+/);
  await expect(userMenu.locator(".user-menu-copy span")).toContainText(/@/);

  const logoutButton = userMenu.getByRole("button", { name: "Log out" });
  await expect(logoutButton).toBeVisible();

  await logoutButton.click();
  await expect(page).toHaveURL(/\/auth\/sign-in$/);
  await expect(page.getByRole("button", { name: "Sign in with Entra ID" })).toBeVisible();
});
