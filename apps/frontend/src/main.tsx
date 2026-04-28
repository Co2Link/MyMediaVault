import React from "react";
import ReactDOM from "react-dom/client";
import { MsalProvider } from "@azure/msal-react";
import { App } from "./app/App";
import { AuthGate } from "./features/auth/AuthGate";
import { initializeAuth, msalInstance } from "./features/auth/msal";
import "./styles.css";

void initializeAuth().then(() => {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <MsalProvider instance={msalInstance}>
        <AuthGate>
          <App />
        </AuthGate>
      </MsalProvider>
    </React.StrictMode>,
  );
});
