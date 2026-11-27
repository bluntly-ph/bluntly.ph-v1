import { AdminListSkeleton, ADMIN_LISTS } from "@/components/admin/AdminSkeletons";

/** Affiliate: Transactions / Months / Imports, Import report, the table, the pager. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminListSkeleton spec={ADMIN_LISTS.affiliate} />;
}
