import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, type Page } from "@playwright/test";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const authDir = path.join(dirname, "..", ".auth");

export function buildAuthFile(filename: string) {
  fs.mkdirSync(authDir, { recursive: true });
  return path.join(authDir, filename);
}

export function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export async function authenticateWithEntra(page: Page, username: string, password: string, authFile: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in with Entra ID" }).click();
  await completeEntraLogin(page, username, password);
  await expect(page.getByRole("heading", { name: "Your media vault" })).toBeVisible({ timeout: 20_000 });
  await page.context().storageState({ path: authFile });
}

async function completeEntraLogin(page: Page, username: string, password: string) {
  const collectionHeading = page.getByRole("heading", { name: "Your media vault" });
  const addVideoLink = page.getByRole("link", { name: "Add video" });
  const signInHeading = page.getByRole("heading", { name: "Sign in" });
  const enterPasswordHeading = page.getByRole("heading", { name: "Enter password" });
  const staySignedInHeading = page.getByRole("heading", { name: "Stay signed in?" });
  const permissionsHeading = page.getByRole("heading", { name: "Permissions requested" });
  const useAnotherAccountButton = page.getByRole("button", { name: /use another account/i });
  const emailInput = page.getByPlaceholder("Email, phone, or Skype");
  const passwordInput = page.getByPlaceholder("Password");
  let submittedUsername = false;

  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (
      page.url().startsWith("http://localhost:3000") &&
      ((await collectionHeading.isVisible().catch(() => false)) || (await addVideoLink.isVisible().catch(() => false)))
    ) {
      return;
    }

    if (await useAnotherAccountButton.isVisible().catch(() => false)) {
      await useAnotherAccountButton.click();
      submittedUsername = false;
      continue;
    }

    if (
      (await enterPasswordHeading.isVisible().catch(() => false)) &&
      (await passwordInput.isVisible().catch(() => false))
    ) {
      try {
        await passwordInput.fill(password, { timeout: 2_000 });
        await page.keyboard.press("Enter");
      } catch {
        await page.waitForTimeout(500);
      }
      continue;
    }

    if (
      !submittedUsername &&
      !(await enterPasswordHeading.isVisible().catch(() => false)) &&
      (await signInHeading.isVisible().catch(() => false)) &&
      (await emailInput.isVisible().catch(() => false))
    ) {
      try {
        await emailInput.fill(username, { timeout: 2_000 });
        await page.keyboard.press("Enter");
        submittedUsername = true;
      } catch {
        await page.waitForTimeout(500);
      }
      continue;
    }

    if (await staySignedInHeading.isVisible().catch(() => false)) {
      await page.getByRole("button", { name: "No" }).click();
      continue;
    }

    if (await permissionsHeading.isVisible().catch(() => false)) {
      await page.getByRole("button", { name: "Accept" }).click();
      continue;
    }

    await page.waitForTimeout(1000);
  }

  throw new Error(`Authentication did not return to the local app. Final URL: ${page.url()}`);
}
