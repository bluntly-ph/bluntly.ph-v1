import { ProfilePageSkeleton } from "@/components/profile/ProfilePageSkeleton";
import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";

/** A member's public profile while it loads: their card beside the Reviews tab and their reviews. */
export default function Loading() {
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      <SiteHeaderSkeleton />
      <ProfilePageSkeleton label="Loading this profile" tabs={1} />
    </div>
  );
}
