"use client";

import { useRouter } from "next/navigation";
import { useRef } from "react";
import { PencilSimple, ShareNetwork } from "@phosphor-icons/react";

import { ShareSheet, type ShareSheetHandle } from "@/components/share/ShareSheet";
import { OverflowMenu } from "@/components/ui/OverflowMenu";

/**
 * The owner's "⋯" on their own profile (owner, 2026-09-28): Share profile —
 * the app's share sheet, with the public `/u/…` address, never the private
 * `/profile` — and Edit profile. It replaces the panel's separate share icon
 * and the Edit profile chip; Log out lives in the side navigation.
 */
export function ProfileMenu({ name, path }: { name: string; path: string }) {
  const router = useRouter();
  const sheet = useRef<ShareSheetHandle>(null);
  return (
    <>
      <OverflowMenu
        label="Profile options"
        items={[
          {
            key: "share",
            label: "Share profile",
            icon: <ShareNetwork size={18} aria-hidden="true" />,
            onSelect: () => sheet.current?.open(),
          },
          {
            key: "edit",
            label: "Edit profile",
            icon: <PencilSimple size={18} aria-hidden="true" />,
            onSelect: () => router.push("/profile/edit"),
          },
        ]}
      />
      <ShareSheet path={path} title={`${name} on bluntly`} variant="none" handle={sheet} />
    </>
  );
}

export default ProfileMenu;
