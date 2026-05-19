import { fileURLToPath } from "node:url";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const userAuthFile = path.join(dirname, ".auth", "user.json");
const headerAuthFile = path.join(dirname, ".auth", "header-user.json");
const adminAuthFile = path.join(dirname, ".auth", "admin.json");

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "user-chromium",
      dependencies: ["setup"],
      testIgnore: [
        /auth\..*\.setup\.ts/,
        /admin-actors-admin\.spec\.ts/,
        /admin-tags-admin\.spec\.ts/,
        /admin-torrents-admin\.spec\.ts/,
        /header\.spec\.ts/,
        /smoke-dev\.spec\.ts/,
      ],
      use: {
        ...devices["Desktop Chrome"],
        storageState: userAuthFile,
      },
    },
    {
      name: "header-chromium",
      dependencies: ["setup"],
      testMatch: /header\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        storageState: headerAuthFile,
      },
    },
    {
      name: "admin-chromium",
      dependencies: ["setup"],
      testMatch: /admin-(actors-admin|tags-admin|torrents-admin)\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        storageState: adminAuthFile,
      },
    },
    {
      name: "smoke-dev-chromium",
      dependencies: ["setup"],
      testMatch: /smoke-dev\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        storageState: userAuthFile,
      },
    },
  ],
});
