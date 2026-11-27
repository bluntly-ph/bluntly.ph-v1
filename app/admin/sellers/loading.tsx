import { AdminListSkeleton, ADMIN_LISTS } from "@/components/admin/AdminSkeletons";

/** Sellers: Claims / Appeals / Product links, the claims table, the pager. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminListSkeleton spec={ADMIN_LISTS.sellers} />;
}
