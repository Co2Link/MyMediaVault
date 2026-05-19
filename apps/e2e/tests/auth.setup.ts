import { test as setup } from "@playwright/test";
import { authenticateWithEntra, buildAuthFile, requireEnv } from "./auth-helpers.js";

setup("authenticate normal and admin users with Entra ID", async ({ browser }) => {
  setup.setTimeout(180_000);

  const userPage = await browser.newPage();
  await authenticateWithEntra(
    userPage,
    requireEnv("E2E_USER_USERNAME"),
    requireEnv("E2E_USER_PASSWORD"),
    buildAuthFile("user.json"),
  );
  await userPage.close();

  const headerUserPage = await browser.newPage();
  await authenticateWithEntra(
    headerUserPage,
    requireEnv("E2E_USER_USERNAME"),
    requireEnv("E2E_USER_PASSWORD"),
    buildAuthFile("header-user.json"),
  );
  await headerUserPage.close();

  const adminPage = await browser.newPage();
  await authenticateWithEntra(
    adminPage,
    requireEnv("E2E_ADMIN_USERNAME"),
    requireEnv("E2E_ADMIN_PASSWORD"),
    buildAuthFile("admin.json"),
  );
  await adminPage.close();
});
