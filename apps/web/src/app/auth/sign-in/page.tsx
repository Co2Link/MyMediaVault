import { redirect } from "next/navigation";
import { signIn } from "@/auth";
import { auth } from "@/auth";

export default async function SignInPage() {
  const session = await auth();
  if (session?.user?.id) {
    redirect("/");
  }

  async function signInAction() {
    "use server";
    await signIn("microsoft-entra-id", { redirectTo: "/" });
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <p className="eyebrow">Private Library</p>
        <h1>MyMediaVault</h1>
        <p className="lede">
          Organize your video collection, preserve metadata history, and move between your library and admin tools
          without leaving the app shell.
        </p>
        <form action={signInAction}>
          <button className="primary-button wide-button" type="submit">
            Sign in with Entra ID
          </button>
        </form>
      </section>
    </main>
  );
}
