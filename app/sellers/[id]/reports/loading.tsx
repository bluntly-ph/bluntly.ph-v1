import { ReportLoading } from "@/components/reports/ReportLoading";
import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";

export default function Loading() {
  return (
    <>
      <SiteHeaderSkeleton />
      <main className="mx-auto w-full min-w-0 max-w-[72rem] flex-1 px-4 py-6 md:px-8 md:py-8">
        <ReportLoading label="the rating summary" sections={1} />
      </main>
    </>
  );
}
