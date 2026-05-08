import Link from "next/link";
import { signOut } from "@/auth";
import { UserMenu } from "@/components/user-menu";
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
        <div className="header-actions">
          <nav aria-label="Primary" className="primary-nav">
            <Link href="/">Collection</Link>
            <Link href="/add">Add video</Link>
            <Link href="/admin/tags">Tags</Link>
            {session.user.isAdmin ? <Link href="/admin/torrents">Torrents</Link> : null}
          </nav>
          <UserMenu
            email={session.user.email}
            image={session.user.image}
            logoutAction={logoutAction}
            name={session.user.name}
          />
        </div>
      ) : null}
    </header>
  );
}
