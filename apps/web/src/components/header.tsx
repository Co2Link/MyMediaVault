import Link from "next/link";
import { signOut } from "@/auth";
import { HeaderActions } from "@/components/header-actions";
import type { AppSession } from "@/lib/auth/session";

export async function Header({ session }: { session: AppSession | null }) {
  async function logoutAction() {
    "use server";
    await signOut({ redirectTo: "/auth/sign-in" });
  }

  return (
    <header className="site-header">
      <div>
        <p className="eyebrow">Private Library</p>
        <Link className="brand-mark" href="/">
          MyMediaVault
        </Link>
      </div>
      {session?.user?.id ? (
        <HeaderActions
          email={session.user.email}
          image={session.user.image}
          isAdmin={Boolean(session.user.isAdmin)}
          logoutAction={logoutAction}
          name={session.user.name}
        />
      ) : null}
    </header>
  );
}
