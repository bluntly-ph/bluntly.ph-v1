import { AdminListSkeleton, ADMIN_LISTS } from "@/components/admin/AdminSkeletons";

/** Payouts: five tabs, three figures, the table, the pager. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminListSkeleton spec={ADMIN_LISTS.payouts} />;
}
