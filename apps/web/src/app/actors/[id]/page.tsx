import Image from "next/image";
import { notFound, redirect } from "next/navigation";
import { auth } from "@/auth";
import { VideoCard } from "@/components/video-card";
import { AppError } from "@/lib/errors";
import { getActorById } from "@/lib/actors";
import { listVideosByActor } from "@/lib/videos";

export default async function ActorProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }

  const { id } = await params;
  let actor;
  let videos;
  try {
    [actor, videos] = await Promise.all([getActorById(id), listVideosByActor(session.user.id, id)]);
  } catch (error) {
    if (error instanceof AppError) {
      notFound();
    }
    throw error;
  }

  return (
    <main className="workspace actor-profile-layout">
      <section className="editor-card actor-profile-card">
        <div className="actor-profile-image">
          {actor.hasProfileImage ? (
            <Image
              alt={`${actor.name} profile image`}
              fill
              priority
              sizes="(max-width: 900px) 100vw, 420px"
              src={`/api/actors/${actor.id}/image?v=${encodeURIComponent(actor.updatedAt)}`}
              unoptimized
            />
          ) : (
            <span>{actor.name.slice(0, 1).toUpperCase()}</span>
          )}
        </div>
        <div className="actor-profile-copy">
          <p className="eyebrow">Actor</p>
          <h1>{actor.name}</h1>
          <p className="muted-copy">{actor.description ?? "No description has been added."}</p>
        </div>
      </section>
      <section>
        <h2>Videos featuring this actor</h2>
        <div className="content-grid">
          {videos.length === 0 ? (
            <div className="empty-panel">
              <h3>No videos in your collection contain this actor.</h3>
            </div>
          ) : (
            videos.map((video) => <VideoCard key={video.id} video={video} />)
          )}
        </div>
      </section>
    </main>
  );
}
