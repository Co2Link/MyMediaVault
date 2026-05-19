import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { AddVideoForm } from "@/app/add/add-video-form";
import { listActors } from "@/lib/actors";
import { listTags } from "@/lib/tags";

export default async function AddPage() {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }

  const [actors, tags] = await Promise.all([listActors(), listTags()]);

  return (
    <main className="workspace">
      <AddVideoForm actors={actors} tags={tags} />
    </main>
  );
}
