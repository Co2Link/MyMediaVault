import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { AddVideoForm } from "@/app/add/add-video-form";

export default async function AddPage() {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }

  return (
    <main className="workspace">
      <AddVideoForm />
    </main>
  );
}
