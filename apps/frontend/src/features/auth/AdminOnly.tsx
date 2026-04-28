import type { PropsWithChildren } from "react";

export function AdminOnly({ children }: PropsWithChildren) {
  const isAdmin = localStorage.getItem("mmv.testAdmin") === "true";
  if (!isAdmin) {
    return <p className="error">Administrator access is required.</p>;
  }
  return <>{children}</>;
}
