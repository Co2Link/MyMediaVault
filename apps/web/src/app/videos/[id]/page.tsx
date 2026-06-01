import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { ActorLinks } from "@/components/actor-links";
import { MetadataStatusBadge } from "@/components/metadata-status";
import { TagLinks } from "@/components/tag-links";
import { VideoPreviewGallery } from "@/components/video-preview-gallery";
import { listActors } from "@/lib/actors";
import { getVideoById } from "@/lib/videos";
import { VideoDetailForm } from "@/app/videos/[id]/video-detail-form";
import { createFileTree, TorrentFileTree } from "@/app/videos/[id]/torrent-file-tree";
import { listTags } from "@/lib/tags";

export default async function VideoDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ created?: string }>;
}) {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }

  const [{ id }, query] = await Promise.all([params, searchParams]);
  const [video, actors, tags] = await Promise.all([getVideoById(session.user.id, id), listActors(), listTags()]);
  const fileTree = createFileTree(video.files);

  return (
    <main className="workspace detail-layout">
      <section className="editor-card">
        <div className="detail-header">
          <div>
            <p className="eyebrow">Detail</p>
            <h1>{video.displayTitle ?? video.infoHash}</h1>
            <p className="muted-copy">{video.torrentName ?? video.infoHash}</p>
          </div>
          <MetadataStatusBadge error={video.metadataError} status={video.metadataStatus} />
        </div>
        {query.created === "1" ? <p className="success-copy">Video added. Metadata processing has been queued.</p> : null}
        <VideoPreviewGallery preview={video.preview} videoId={video.id} />
        <dl className="detail-meta-grid">
          <div>
            <dt>Actors</dt>
            <dd>
              <ActorLinks actors={video.actors} />
            </dd>
          </div>
          <div>
            <dt>Tags</dt>
            <dd>
              <TagLinks tags={video.tags} />
            </dd>
          </div>
        </dl>
        <VideoDetailForm actors={actors} tags={tags} video={video} />
      </section>
      <aside className="editor-card">
        <h2>Torrent files</h2>
        {video.files.length === 0 ? (
          <p className="muted-copy">Files will appear after metadata finishes processing.</p>
        ) : (
          <TorrentFileTree node={fileTree} />
        )}
      </aside>
    </main>
  );
}
