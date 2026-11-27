import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";
import { Bar, Block, Circle, Pill, SkeletonRegion } from "@/components/ui/Skeleton";

/**
 * A question while it loads, on the page's own grid (the 44rem reading column
 * and the 18rem card from `lg`): All questions, what it is about, who asked,
 * the question, its actions, the answers; at the right, the questions-about
 * card with its figures and two buttons.
 */
export default function Loading() {
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-card)]">
      <SiteHeaderSkeleton />
      <SkeletonRegion
        label="Loading the question"
        className="mx-auto w-full max-w-[42rem] flex-1 px-4 pb-16 pt-4 md:px-6 lg:grid lg:max-w-[72rem] lg:grid-cols-[minmax(0,44rem)_18rem] lg:items-start lg:justify-center lg:gap-12 lg:px-10 lg:pt-10"
      >
        <div className="flex flex-col">
          <Bar size={10} className="w-24" />
          <div className="mt-4 flex items-center gap-3 rounded-[16px] bg-[var(--surface-card)] p-3 shadow-[var(--shadow-card)]">
            <Block className="size-12" />
            <span className="flex flex-col gap-2">
              <Bar size={14} className="w-40" />
              <Bar size={8} className="w-20" />
            </span>
          </div>
          <span className="mt-6 flex items-center gap-2">
            <Circle size={20} />
            <Bar size={8} className="w-32" />
          </span>
          <Bar size={18} className="mt-4 w-4/5" />
          <span className="mt-4 flex items-center gap-3">
            <Bar size={10} className="w-8" />
            <Bar size={10} className="w-8" />
            <span className="flex-1" />
            <Pill className="h-8 w-24" />
          </span>
          <Bar size={14} className="mt-8 w-20" />
          {Array.from({ length: 2 }, (_, i) => (
            <div key={i} className="mt-5 flex gap-3">
              <Circle size={32} />
              <span className="flex flex-1 flex-col gap-2">
                <Bar size={10} className="w-36" />
                <Bar size={8} className="w-20" />
                <Bar size={10} className="mt-2 w-full" />
                <Bar size={10} className="w-2/3" />
              </span>
            </div>
          ))}
        </div>
        <div className="mt-8 hidden rounded-[16px] bg-[var(--surface-card)] p-6 shadow-[var(--shadow-card)] lg:mt-0 lg:block">
          <Bar size={8} className="w-28" />
          <Bar size={14} className="mt-2 w-40" />
          <div className="mt-5 grid grid-cols-2 gap-3 border-t border-[var(--line-hairline-10)] pt-4">
            {Array.from({ length: 2 }, (_, i) => (
              <span key={i} className="flex flex-col gap-2">
                <Bar size={8} className="w-14" />
                <Bar size={14} className="w-6" />
              </span>
            ))}
          </div>
          <Pill className="mt-5 h-11 w-full" />
          <Pill className="mt-3 h-11 w-full" />
        </div>
      </SkeletonRegion>
    </div>
  );
}
