import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { TagAdminPanel } from "@/app/admin/tags/tag-admin-panel";
import { AdminCatalogFilter } from "@/components/admin-catalog-filter";
import { PaginationLinks } from "@/components/pagination-links";
import { firstQueryValue, paginate } from "@/lib/pagination";
import { listTags } from "@/lib/tags";

export default async function AdminTagsPage({
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
          <h1>Tags</h1>
          <p className="error-copy">Administrator access is required.</p>
        </section>
      </main>
    );
  }

  const query = await searchParams;
  const q = firstQueryValue(query.q)?.trim() ?? "";
  const normalizedQuery = q.toLowerCase();
  const tags = (await listTags()).filter((tag) => tag.name.toLowerCase().includes(normalizedQuery));
  const page = paginate(tags, firstQueryValue(query.page), 8);

  return (
    <main className="workspace">
      <AdminCatalogFilter query={q} />
      <TagAdminPanel tags={page.items} />
      <PaginationLinks page={page.page} pageCount={page.pageCount} pathname="/admin/tags" query={q ? { q } : {}} />
    </main>
  );
}
