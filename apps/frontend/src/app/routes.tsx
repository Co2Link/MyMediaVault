import { AdminOnly } from "../features/auth/AdminOnly";
import { AdminTagManagementPage } from "../features/tags/AdminTagManagementPage";
import { AddVideoForm } from "../features/videos/AddVideoForm";
import { CollectionPage } from "../features/videos/CollectionPage";
import { VideoDetailPage } from "../features/videos/VideoDetailPage";

export type RouteName = "collection" | "add" | "detail" | "admin";

export function renderRoute(route: RouteName, selectedVideoId?: string, onSelectVideo?: (videoId: string) => void) {
  if (route === "add") return <AddVideoForm />;
  if (route === "detail" && selectedVideoId) return <VideoDetailPage videoId={selectedVideoId} />;
  if (route === "admin") {
    return (
      <AdminOnly>
        <AdminTagManagementPage />
      </AdminOnly>
    );
  }
  return <CollectionPage onSelectVideo={onSelectVideo} />;
}
