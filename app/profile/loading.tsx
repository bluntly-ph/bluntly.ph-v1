import { ProfilePageSkeleton } from "@/components/profile/ProfilePageSkeleton";
import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";

/** Your profile while it loads: the profile card beside its tabs and reviews (ProfileLayout's grid). */
export default function Loading() {
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      <SiteHeaderSkeleton />
      <ProfilePageSkeleton label="Loading your profile" tabs={4} />
    </div>
  );
}
