import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";
import { Bar, Circle, Pill } from "@/components/ui/Skeleton";

/** Screen/Messages/Loading (Figma 8313:31968). */
export default function Loading() {
  return (
    <>
      <div className="hidden md:block">
        <SiteHeaderSkeleton />
      </div>
      <div role="status" aria-busy="true" aria-live="polite" className="mx-auto flex min-h-dvh w-full max-w-[480px] flex-col gap-4 bg-[var(--surface-card)] px-4 pt-20">
        <span className="sr-only">Loading messages</span>
        <Bar size={18} className="my-[5px] w-40" />
        <Bar size={10} className="w-4/5" />
        <div className="flex gap-2">
          <Pill className="h-8 w-20" />
          <Pill className="h-8 w-24" />
        </div>
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="flex gap-3 rounded-[16px] border border-[var(--border-subtle)] p-3">
            <Circle size={32} />
            <span className="flex flex-1 flex-col gap-2">
              <Bar size={10} className="w-3/5" />
              <Bar size={10} className="w-4/5" />
            </span>
          </div>
        ))}
      </div>
    </>
  );
}
