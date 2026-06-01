"use client";

import Link from "next/link";
import { useState } from "react";
import { UserMenu } from "@/components/user-menu";

export function HeaderActions({
  email,
  image,
  isAdmin,
  logoutAction,
  name,
}: {
  email: string | null | undefined;
  image: string | null | undefined;
  isAdmin: boolean;
  logoutAction: () => Promise<void>;
  name: string | null | undefined;
}) {
  const [navigationOpen, setNavigationOpen] = useState(false);

  return (
    <div className="header-actions">
      <div className="mobile-header-controls">
        <button
          aria-expanded={navigationOpen}
          aria-label={navigationOpen ? "Close navigation menu" : "Open navigation menu"}
          className="ghost-button mobile-nav-toggle"
          onClick={() => setNavigationOpen((open) => !open)}
          type="button"
        >
          Menu
        </button>
      </div>
      <nav aria-label="Primary" className={`primary-nav${navigationOpen ? " primary-nav-open" : ""}`}>
        <Link href="/">Collection</Link>
        <Link href="/add">Add video</Link>
        {isAdmin ? (
          <>
            <Link href="/admin/tags">Tags</Link>
            <Link href="/admin/actors">Actors</Link>
            <Link href="/admin/torrents">Torrents</Link>
          </>
        ) : null}
      </nav>
      <UserMenu email={email} image={image} logoutAction={logoutAction} name={name} />
    </div>
  );
}
