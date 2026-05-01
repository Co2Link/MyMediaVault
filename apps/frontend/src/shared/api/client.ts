import { loginRequest } from "../../features/auth/config";
import { msalInstance } from "../../features/auth/msal";

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

function getRequiredApiBaseUrl(): string {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("Missing VITE_API_BASE_URL. The frontend must be built with the deployed backend URL.");
  }
  return apiBaseUrl;
}

export const API_BASE_URL = getRequiredApiBaseUrl();

async function authHeaders(): Promise<Record<string, string>> {
  const account = msalInstance.getActiveAccount() ?? msalInstance.getAllAccounts()[0];
  if (!account) {
    await msalInstance.loginRedirect(loginRequest);
    throw new Error("Sign-in is required before calling the API.");
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
