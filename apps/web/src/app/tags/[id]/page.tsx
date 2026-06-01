import { notFound, redirect } from "next/navigation";
import { auth } from "@/auth";
import { VideoCard } from "@/components/video-card";
import { AppError } from "@/lib/errors";
import { getTagById } from "@/lib/tags";
import { listVideosByTag } from "@/lib/videos";

export default async function TagPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }

  const { id } = await params;
  let tag;
  let videos;
  try {
    [tag, videos] = await Promise.all([getTagById(id), listVideosByTag(session.user.id, id)]);
  } catch (error) {
    if (error instanceof AppError) {
      notFound();
    }
    throw error;
  }

  return (
    <main className="workspace">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Tag</p>
          <h1>{tag.name}</h1>
          <p className="lede">Videos in your collection tagged with this label.</p>
        </div>
      </section>
      <section className="content-grid">
        {videos.length === 0 ? (
          <div className="empty-panel">
            <h2>No videos in your collection contain this tag.</h2>
          </div>
        ) : (
          videos.map((video) => <VideoCard key={video.id} video={video} />)
        )}
      </section>
    </main>
  );
}
