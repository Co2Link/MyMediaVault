import { PublicClientApplication } from "@azure/msal-browser";
import { authConfig, isProductionAuthEnabled } from "./config";

export const msalInstance = new PublicClientApplication({
  auth: {
    clientId: authConfig.clientId,
    authority: authConfig.tenantId ? `https://login.microsoftonline.com/${authConfig.tenantId}` : undefined,
    redirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: "localStorage",
  },
});

export async function initializeAuth() {
  if (!isProductionAuthEnabled) return;
  await msalInstance.initialize();
  const result = await msalInstance.handleRedirectPromise();
  const account = result?.account ?? msalInstance.getAllAccounts()[0];
  if (account) {
    msalInstance.setActiveAccount(account);
  }
}
