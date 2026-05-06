"use client";

import Image from "next/image";
import { useState } from "react";

export function AvatarImage({
  name,
  image,
  size = 40,
}: {
  name: string | null | undefined;
  image: string | null | undefined;
  size?: number;
}) {
  const [failed, setFailed] = useState(false);
  const initials = (name ?? "User")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  if (failed || !image) {
    return (
      <span
        aria-hidden="true"
        className="avatar-fallback"
        style={{ width: size, height: size }}
      >
        {initials || "U"}
      </span>
    );
  }

  return (
    <Image
      alt={`${name ?? "User"} profile photo`}
      className="avatar-image"
      height={size}
      src={image}
      unoptimized
      width={size}
      onError={() => setFailed(true)}
    />
  );
}
