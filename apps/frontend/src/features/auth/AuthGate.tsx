import { useMsal } from "@azure/msal-react";
import type { PropsWithChildren } from "react";
import { isProductionAuthEnabled, loginRequest } from "./config";

export function AuthGate({ children }: PropsWithChildren) {
  const { accounts, instance } = useMsal();

  if (!isProductionAuthEnabled) {
    return <>{children}</>;
  }

  if (accounts.length === 0) {
    return (
      <main className="auth-screen">
        <section className="auth-panel">
          <h1>MyMediaVault</h1>
          <p>Sign in to manage your video collection.</p>
          <button className="primary-button" type="button" onClick={() => void instance.loginRedirect(loginRequest)}>
            Sign in
          </button>
        </section>
      </main>
    );
  }

  if (!instance.getActiveAccount()) {
    instance.setActiveAccount(accounts[0]);
  }

  return <>{children}</>;
}
