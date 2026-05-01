export const authConfigurationError =
  "Missing Entra auth configuration. Set VITE_ENTRA_TENANT_ID, VITE_ENTRA_CLIENT_ID, and VITE_API_SCOPE.";

type AuthConfig = {
  tenantId: string;
  clientId: string;
  apiScope: string;
};

function getRequiredAuthConfig(): AuthConfig {
  const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID;
  const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID;
  const apiScope = import.meta.env.VITE_API_SCOPE;

  if (!tenantId || !clientId || !apiScope) {
    throw new Error(authConfigurationError);
  }

  return { tenantId, clientId, apiScope };
}

export const authConfig = getRequiredAuthConfig();

export const loginRequest = {
  scopes: [authConfig.apiScope],
};
