"use client";

import { useState } from "react";
import { AvatarImage } from "@/components/avatar-image";

export function UserMenu({
  name,
  email,
  image,
  logoutAction,
}: {
  name: string | null | undefined;
  email: string | null | undefined;
  image: string | null | undefined;
  logoutAction: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="user-menu">
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={open ? "Close user menu" : "Open user menu"}
        className="avatar-button"
        type="button"
        onClick={() => setOpen((value) => !value)}
      >
        <AvatarImage image={image ?? "/api/me/photo"} name={name} />
      </button>
      {open ? (
        <div className="user-menu-panel" role="menu">
          <div className="user-menu-copy">
            <strong>{name ?? "Signed in user"}</strong>
            <span>{email ?? "No email available"}</span>
          </div>
          <form action={logoutAction}>
            <button className="ghost-button danger-button wide-button" type="submit">
              Log out
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}
