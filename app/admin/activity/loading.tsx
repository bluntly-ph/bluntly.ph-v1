import { AdminActivitySkeleton } from "@/components/admin/AdminSkeletons";

/** Activity log: filters, day cards, the side panel. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminActivitySkeleton />;
}
