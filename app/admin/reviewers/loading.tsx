import { AdminListSkeleton, ADMIN_LISTS } from "@/components/admin/AdminSkeletons";

/** People: four tabs, the seven-column table, the pager. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminListSkeleton spec={ADMIN_LISTS.people} />;
}
