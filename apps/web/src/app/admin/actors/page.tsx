import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { ActorAdminPanel } from "@/app/admin/actors/actor-admin-panel";
import { AdminCatalogFilter } from "@/components/admin-catalog-filter";
import { PaginationLinks } from "@/components/pagination-links";
import { listActors } from "@/lib/actors";
import { firstQueryValue, paginate } from "@/lib/pagination";

export default async function AdminActorsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string | string[]; q?: string | string[] }>;
}) {
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

  const query = await searchParams;
  const q = firstQueryValue(query.q)?.trim() ?? "";
  const normalizedQuery = q.toLowerCase();
  const actors = (await listActors()).filter((actor) =>
    [actor.name, actor.description].some((value) => value?.toLowerCase().includes(normalizedQuery)),
  );
  const page = paginate(actors, firstQueryValue(query.page), 8);

  return (
    <main className="workspace">
      <AdminCatalogFilter query={q} />
      <ActorAdminPanel actors={page.items} />
      <PaginationLinks page={page.page} pageCount={page.pageCount} pathname="/admin/actors" query={q ? { q } : {}} />
    </main>
  );
}
