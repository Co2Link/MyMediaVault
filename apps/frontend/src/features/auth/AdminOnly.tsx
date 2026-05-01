import { useMsal } from "@azure/msal-react";
import type { PropsWithChildren } from "react";

export function AdminOnly({ children }: PropsWithChildren) {
  const { accounts, instance } = useMsal();
  const account = instance.getActiveAccount() ?? accounts[0];
  const claims = account?.idTokenClaims as { roles?: string[] } | undefined;
  const roles = claims?.roles ?? [];
  if (!roles.some((role) => role === "Admin" || role === "MyMediaVault.Admin")) {
    return <p className="error">Administrator access is required.</p>;
  }
  return <>{children}</>;
}
