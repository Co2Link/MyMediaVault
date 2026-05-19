import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { ActorAdminPanel } from "@/app/admin/actors/actor-admin-panel";
import { listActors } from "@/lib/actors";

export default async function AdminActorsPage() {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }
  if (!session.user.isAdmin) {
    return (
      <main className="workspace">
        <section className="editor-card">
          <h1>Actors</h1>
          <p className="error-copy">Administrator access is required.</p>
        </section>
      </main>
    );
  }

  const actors = await listActors();

  return (
    <main className="workspace">
      <ActorAdminPanel actors={actors} />
    </main>
  );
}
