import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { AddVideoForm } from "@/app/add/add-video-form";
import { listTags } from "@/lib/tags";

export default async function AddPage() {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }

  const tags = await listTags();

  return (
    <main className="workspace">
      <AddVideoForm tags={tags} />
    </main>
  );
}
