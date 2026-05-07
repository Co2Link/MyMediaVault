import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { TagAdminPanel } from "@/app/admin/tags/tag-admin-panel";
import { listTags } from "@/lib/tags";

export default async function AdminTagsPage() {
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

  const tags = ((await listTags()) as unknown as Array<{ id?: string; _id?: string; name: string }>).map((tag) => ({
    id: tag.id ?? tag._id ?? "",
    name: tag.name,
  }));

  return (
    <main className="workspace">
      <TagAdminPanel tags={tags} />
    </main>
  );
}
