import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { MetadataStatusBadge } from "@/components/metadata-status";
import { getVideoById } from "@/lib/videos";
import { VideoDetailForm } from "@/app/videos/[id]/video-detail-form";
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
  const [video, tags] = await Promise.all([getVideoById(session.user.id, id), listTags()]);

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
        <VideoDetailForm tags={tags} video={video} />
      </section>
      <aside className="editor-card">
        <h2>Torrent files</h2>
        {video.files.length === 0 ? (
          <p className="muted-copy">Files will appear after metadata finishes processing.</p>
        ) : (
          <ul className="file-list">
            {video.files.map((file) => (
              <li key={file.path}>
                <span>{file.path}</span>
                <span>{file.sizeBytes} bytes</span>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </main>
  );
}
