import Image from "next/image";
import { notFound, redirect } from "next/navigation";
import { auth } from "@/auth";
import { AppError } from "@/lib/errors";
import { getActorById } from "@/lib/actors";

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
  try {
    actor = await getActorById(id);
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
    </main>
  );
}
