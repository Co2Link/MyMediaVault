import { useState } from "react";
import { renderRoute, type RouteName } from "./routes";

export function App() {
  const [route, setRoute] = useState<RouteName>("collection");

  return (
    <main className="app-shell">
      <header className="topbar">
        <h1>MyMediaVault</h1>
        <nav aria-label="Primary">
          <button type="button" onClick={() => setRoute("collection")}>Collection</button>
          <button type="button" onClick={() => setRoute("add")}>Add video</button>
          <button type="button" onClick={() => setRoute("admin")}>Tags</button>
        </nav>
      </header>
      <section className="workspace">{renderRoute(route)}</section>
    </main>
  );
}
