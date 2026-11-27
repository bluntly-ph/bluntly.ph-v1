import { BrowseLayout } from "@/components/site/BrowseRails";
import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";
import { Bar, Pill, SkeletonRegion } from "@/components/ui/Skeleton";

/** Q&A while it loads: the heading and Ask a question, then divided rows (when,
 * store, the question, its answers), and the side rail from `xl`. */
export default function Loading() {
  return (
    <>
      <SiteHeaderSkeleton />
      <BrowseLayout
        current="questions"
        outerClassName="mx-auto w-full max-w-[42rem] flex-1 pb-16 pt-5 md:px-6 lg:max-w-[76rem] lg:px-10 lg:py-10"
        aside={
          <div className="flex flex-col gap-8">
            {[5, 4].map((lines, g) => (
              <span key={g} className="flex flex-col gap-3">
                <Bar size={10} className="w-20" />
                {Array.from({ length: lines }, (_, i) => (
                  <Bar key={i} size={10} className={i % 2 ? "w-28" : "w-full"} />
                ))}
              </span>
            ))}
          </div>
        }
      >
        <SkeletonRegion label="Loading questions" className="flex flex-col px-6 md:px-0">
          {/* Title + "Ask a question" (134px): the title bar is narrower on a phone,
              where 224 + 128 overran a 320px screen by 80px. */}
          <div className="flex items-center gap-3">
            <Bar size={18} className="w-28 sm:w-56" />
            <span className="flex-1" />
            <Pill className="h-8 w-32" />
          </div>
          <Bar size={10} className="mt-3 w-80 max-w-full" />
          <ul className="mt-4">
            {Array.from({ length: 6 }, (_, i) => (
              <li key={i} className="flex flex-col gap-2.5 border-t border-[var(--line-hairline-10)] py-4">
                <Bar size={8} className="w-16" />
                <Bar size={14} className="w-48" />
                <Bar size={10} className="w-72 max-w-full" />
                <Bar size={8} className="w-20" />
              </li>
            ))}
          </ul>
        </SkeletonRegion>
      </BrowseLayout>
    </>
  );
}
