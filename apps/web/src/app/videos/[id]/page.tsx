import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { MetadataStatusBadge } from "@/components/metadata-status";
import { VideoPreviewGallery } from "@/components/video-preview-gallery";
import { getVideoById } from "@/lib/videos";
import { VideoDetailForm } from "@/app/videos/[id]/video-detail-form";
import { listTags } from "@/lib/tags";
import type { TorrentFileRead } from "@/lib/types";

type FileTreeNode = {
  children: Map<string, FileTreeNode>;
  file: TorrentFileRead | null;
  name: string;
};

function createFileTree(files: TorrentFileRead[]) {
  const root: FileTreeNode = { children: new Map(), file: null, name: "" };

  for (const file of files) {
    const parts = file.path.split(/[\\/]+/).filter(Boolean);
    const pathParts = parts.length > 0 ? parts : [file.path];
    let current = root;

    for (const [index, part] of pathParts.entries()) {
      const existing = current.children.get(part);
      const next = existing ?? { children: new Map(), file: null, name: part };
      current.children.set(part, next);
      current = next;

      if (index === pathParts.length - 1) {
        current.file = file;
      }
    }
  }

  return root;
}

function sortedNodes(node: FileTreeNode) {
  return [...node.children.values()].sort((left, right) => {
    if (left.file && !right.file) return 1;
    if (!left.file && right.file) return -1;
    return left.name.localeCompare(right.name, undefined, { sensitivity: "base" });
  });
}

function formatFileSize(sizeBytes: number) {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
    style: "unit",
    unit: "byte",
    unitDisplay: "narrow",
  }).format(sizeBytes);
}

function TorrentFileTree({ node }: { node: FileTreeNode }) {
  return (
    <ul className="file-tree">
      {sortedNodes(node).map((child) => {
        const childNodes = sortedNodes(child);

        if (childNodes.length > 0) {
          return (
            <li className="file-tree-folder" key={child.name}>
              <details open>
                <summary>{child.name}</summary>
                <TorrentFileTree node={child} />
              </details>
            </li>
          );
        }

        return (
          <li className="file-tree-file" key={child.file?.path ?? child.name}>
            <span>{child.name}</span>
            {child.file ? <span>{formatFileSize(child.file.sizeBytes)}</span> : null}
          </li>
        );
      })}
    </ul>
  );
}

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
        <VideoDetailForm tags={tags} video={video} />
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
