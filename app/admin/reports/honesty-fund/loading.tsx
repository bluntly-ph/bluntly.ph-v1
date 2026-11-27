import { AdminReportFrameSkeleton } from "@/components/admin/AdminSkeletons";

/** Honesty Fund report: four figures, two tables. The shell around it is real (see AdminSkeletons). */
export default function Loading() {
  return <AdminReportFrameSkeleton figures={4} tables={2} label="Loading the Honesty Fund report" />;
}
