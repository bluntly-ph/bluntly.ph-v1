import { AdminOverviewSkeleton } from "@/components/admin/AdminSkeletons";

/** /admin: the Overview's cards. Also what a child route without its own loading.tsx shows. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminOverviewSkeleton />;
}
