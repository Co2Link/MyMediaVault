import { useState } from "react";
import { renderRoute, type RouteName } from "./routes";

export function App() {
  const [route, setRoute] = useState<RouteName>("collection");
  const [selectedVideoId, setSelectedVideoId] = useState<string | undefined>();

  function showCollection() {
    setRoute("collection");
    setSelectedVideoId(undefined);
  }

  function showVideoDetail(videoId: string) {
    setSelectedVideoId(videoId);
    setRoute("detail");
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <h1>MyMediaVault</h1>
        <nav aria-label="Primary">
          <button type="button" onClick={showCollection}>Collection</button>
          <button type="button" onClick={() => setRoute("add")}>Add video</button>
          <button type="button" onClick={() => setRoute("admin")}>Tags</button>
        </nav>
      </header>
      <section className="workspace">{renderRoute(route, selectedVideoId, showVideoDetail)}</section>
    </main>
  );
}
