import { loginRequest, isProductionAuthEnabled } from "../../features/auth/config";
import { msalInstance } from "../../features/auth/msal";
import { getTestAuthHeaders } from "../../features/auth/testMode";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export type ApiOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
};

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function authHeaders(): Promise<Record<string, string>> {
  if (!isProductionAuthEnabled) {
    return getTestAuthHeaders();
  }

  const account = msalInstance.getActiveAccount() ?? msalInstance.getAllAccounts()[0];
  if (!account) {
    await msalInstance.loginRedirect(loginRequest);
    return {};
  }

  const result = await msalInstance.acquireTokenSilent({ ...loginRequest, account }).catch(() =>
    msalInstance.acquireTokenPopup({ ...loginRequest, account }),
  );
  return { Authorization: `Bearer ${result.accessToken}` };
}

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
      ...(options.headers ?? {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ message: response.statusText }));
    throw new ApiError(response.status, payload.message ?? response.statusText);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
