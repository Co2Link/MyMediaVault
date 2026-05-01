import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test as setup, expect } from "@playwright/test";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const authDir = path.join(dirname, "..", ".auth");
const authFile = path.join(authDir, "user.json");

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

async function waitForAppOrStaySignedIn(page: Parameters<typeof setup>[1]["page"]) {
  const appHeading = page.getByRole("heading", { name: "MyMediaVault" });
  const staySignedInHeading = page.getByRole("heading", { name: "Stay signed in?" });

  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (page.url().startsWith("http://localhost:5173")) {
      return;
    }

    if (await staySignedInHeading.isVisible().catch(() => false)) {
      await page.getByRole("button", { name: "No" }).click();
    }

    if (await appHeading.isVisible().catch(() => false)) {
      return;
    }

    await page.waitForTimeout(1000);
  }

  throw new Error(`Authentication did not return to the local app. Final URL: ${page.url()}`);
}

setup("authenticate standard user with Entra ID", async ({ page }) => {
  const username = requireEnv("E2E_ENTRA_USERNAME");
  const password = requireEnv("E2E_ENTRA_PASSWORD");

  fs.mkdirSync(authDir, { recursive: true });

  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();

  await page.locator('input[name="loginfmt"]').fill(username);
  await page.locator("#idSIButton9").click();

  await page.locator('input[name="passwd"]').fill(password);
  await page.locator("#idSIButton9").click();

  await waitForAppOrStaySignedIn(page);
  await expect(page.getByRole("heading", { name: "MyMediaVault" })).toBeVisible({ timeout: 20000 });
  await page.context().storageState({ path: authFile });
});
