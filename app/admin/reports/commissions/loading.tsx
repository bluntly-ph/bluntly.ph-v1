import { AdminReportFrameSkeleton } from "@/components/admin/AdminSkeletons";

/** Commissions & Payouts report: eight figures, four tables. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminReportFrameSkeleton figures={8} tables={4} label="Loading the commissions report" />;
}
