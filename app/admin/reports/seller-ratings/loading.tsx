import { AdminReportFrameSkeleton } from "@/components/admin/AdminSkeletons";

/** Seller ratings: heading, the search, the stores table. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminReportFrameSkeleton figures={0} tables={1} label="Loading seller ratings" />;
}
