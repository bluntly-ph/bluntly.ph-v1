import { AdminQueueSkeleton } from "@/components/admin/AdminSkeletons";

/** Review queue: tabs, the Queue switch, the 7-column table, the pager. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminQueueSkeleton />;
}
