export const authConfig = {
  tenantId: import.meta.env.VITE_ENTRA_TENANT_ID ?? "",
  clientId: import.meta.env.VITE_ENTRA_CLIENT_ID ?? "",
  apiScope: import.meta.env.VITE_API_SCOPE ?? "",
};

export const isProductionAuthEnabled = Boolean(authConfig.tenantId && authConfig.clientId && authConfig.apiScope);

export const loginRequest = {
  scopes: authConfig.apiScope ? [authConfig.apiScope] : [],
};
