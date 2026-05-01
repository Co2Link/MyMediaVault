import "@testing-library/jest-dom/vitest";
import type { ReactNode } from "react";
import { vi } from "vitest";

const mockAccount = {
  username: "test.user@example.test",
  idTokenClaims: { roles: ["Admin"] },
};

const mockMsalInstance = {
  initialize: vi.fn().mockResolvedValue(undefined),
  handleRedirectPromise: vi.fn().mockResolvedValue(null),
  getAllAccounts: vi.fn(() => [mockAccount]),
  getActiveAccount: vi.fn(() => mockAccount),
  setActiveAccount: vi.fn(),
  loginRedirect: vi.fn().mockResolvedValue(undefined),
  acquireTokenSilent: vi.fn().mockResolvedValue({ accessToken: "test-access-token" }),
  acquireTokenPopup: vi.fn().mockResolvedValue({ accessToken: "test-access-token" }),
};

vi.mock("../features/auth/msal", () => ({
  msalInstance: mockMsalInstance,
  initializeAuth: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@azure/msal-react", () => ({
  MsalProvider: ({ children }: { children: ReactNode }) => children,
  useMsal: () => ({ accounts: [mockAccount], instance: mockMsalInstance }),
}));
