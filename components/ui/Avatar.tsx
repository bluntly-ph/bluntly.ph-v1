"use client";

import Image from "next/image";
import { useState } from "react";

import { usablePhoto } from "@/lib/image";

/**
 * The one member avatar: the member's own profile photo when there is one,
 * else — and when the photo fails to load — their initial on grey. Figma
 * draws it as a circle (Author 7659:5991: 36px; OthersSaid 7718:12969: 20px
 * with a white ring; Admin People rows: 32px).
 *
 * NO PHOTO = NO DEFAULT PHOTO: `url` is the member's own avatar_url and
 * nothing else; a missing photo is the initial, never a stock image.
 */
export function Avatar({
  name,
  url,
  size = 36,
  ring = false,
  className = "",
}: {
  name: string;
  url: string | null | undefined;
  size?: number;
  /** A white 1.5px ring, for avatars that overlap (OthersSaid). */
  ring?: boolean;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const src = failed ? null : usablePhoto(url ?? null);
  const initial = name.replace(/^@/, "").trim().slice(0, 1).toUpperCase() || "?";
  return (
    <span
      className={`relative grid shrink-0 place-items-center overflow-hidden rounded-full bg-[var(--base-gray-200)] font-medium text-[var(--text-secondary)] ${ring ? "ring-[1.5px] ring-[var(--surface-card)]" : ""} ${className}`}
      style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size / 3)) }}
      data-testid="avatar"
    >
      {src ? (
        <Image src={src} alt="" fill sizes={`${size}px`} className="object-cover" onError={() => setFailed(true)} />
      ) : (
        <span aria-hidden="true">{initial}</span>
      )}
    </span>
  );
}
