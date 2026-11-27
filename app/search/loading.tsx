import { BrowseLayout } from "@/components/site/BrowseRails";
import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";
import { Bar, Block, Circle, Pill, SkeletonRegion } from "@/components/ui/Skeleton";

/**
 * Search results while they load. The page is a list, not a grid: the search
 * field, the four tabs, "Results for …", then rows (avatar and meta line, the
 * title, the helpful line, a 100 / 120 px thumbnail at the right), inside the
 * same BrowseLayout as the loaded page — its navigation rail is static, so it
 * renders for real, and the Refine rail keeps its width from `xl`.
 */
export default function Loading() {
  return (
    <>
      <SiteHeaderSkeleton showSearch={false} />
      <main className="flex flex-1 flex-col">
        <BrowseLayout
          current="reviews"
          outerClassName="mx-auto flex w-full max-w-[52rem] flex-1 flex-col px-4 pb-8 pt-3 md:px-6 md:py-8 lg:max-w-[76rem] lg:px-10 lg:py-10"
          contentClassName="flex flex-1 flex-col"
          aside={
            <div className="flex flex-col gap-8">
              {[3, 3, 4, 3].map((links, g) => (
                <span key={g} className="flex flex-col gap-3">
                  <Bar size={10} className="w-20" />
                  {Array.from({ length: links }, (_, i) => (
                    <Bar key={i} size={10} className={i === 0 ? "w-24" : "w-16"} />
                  ))}
                </span>
              ))}
            </div>
          }
        >
          <SkeletonRegion label="Searching" className="flex flex-col">
            <Pill className="h-12 w-full" />
            <div className="-mx-4 mt-[22px] flex gap-8 border-b border-[var(--line-hairline-10)] px-4 pb-3 md:mx-0 md:mt-5 md:gap-6 md:px-0">
              {/* As wide as the real labels: 12px text on a phone (48/60/39/41 px at
                  320), 14px from md. The 14px widths overran a 320px screen by 48px. */}
              {["w-12 md:w-16", "w-[60px] md:w-20", "w-10 md:w-14", "w-10 md:w-14"].map((w, i) => (
                <Bar key={i} size={14} className={w} />
              ))}
            </div>
            <Bar size={18} className="mt-8 w-48" />
            <ul className="mt-4 border-t border-[var(--line-hairline-10)]">
              {Array.from({ length: 5 }, (_, i) => (
                <li
                  key={i}
                  className="flex items-start justify-between gap-4 border-b border-[var(--line-hairline-10)] px-4 pb-[21px] pt-5 md:px-0 md:py-4 lg:gap-6 lg:py-5"
                >
                  <span className="flex min-w-0 flex-1 flex-col max-md:max-w-[226px]">
                    <span className="flex items-center gap-2">
                      <Circle size={24} />
                      <Bar size={8} className="w-48 max-w-full" />
                    </span>
                    <Bar size={14} className="mt-4 w-4/5" />
                    <Bar size={8} className="mt-3 w-28" />
                  </span>
                  <Block className="size-[100px] lg:size-[120px]" />
                </li>
              ))}
            </ul>
          </SkeletonRegion>
        </BrowseLayout>
      </main>
    </>
  );
}
