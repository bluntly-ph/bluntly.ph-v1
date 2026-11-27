import { AdminListSkeleton, ADMIN_LISTS } from "@/components/admin/AdminSkeletons";

/** Honesty Fund (a Payouts tab): three figures and the cycles table. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminListSkeleton spec={ADMIN_LISTS.honestyFund} />;
}
