import { BrowseLayout } from "@/components/site/BrowseRails";
import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";
import { Bar, Block, Pill, SkeletonRegion } from "@/components/ui/Skeleton";

/** Review requests while they load: the heading, its line and Post a request,
 * then request cards (vote box, the product, title and waiting chip, the ask,
 * the answer link), and "How requests work" from `xl`. */
export default function Loading() {
  return (
    <>
      <SiteHeaderSkeleton />
      <BrowseLayout
        current="requests"
        outerClassName="mx-auto w-full max-w-[52rem] flex-1 px-6 py-8 lg:max-w-[76rem] lg:px-10 lg:py-10"
        aside={
          <div className="flex flex-col gap-8">
            {[7, 4].map((lines, g) => (
              <span key={g} className="flex flex-col gap-3">
                <Bar size={10} className="w-36" />
                {Array.from({ length: lines }, (_, i) => (
                  <Bar key={i} size={10} className={i === lines - 1 ? "w-24" : "w-full"} />
                ))}
              </span>
            ))}
          </div>
        }
      >
        <SkeletonRegion label="Loading requests" className="flex flex-col">
          <Bar size={18} className="my-[5px] w-52" />
          <Bar size={10} className="mt-3 w-full max-w-[36rem]" />
          <Bar size={10} className="mt-2 w-12" />
          <Pill className="mt-4 h-9 w-36" />
          <div className="mt-6 flex flex-col gap-3">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="flex gap-4 rounded-[var(--radius-sm)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)]">
                <Block className="h-[54px] w-11" />
                <span className="flex min-w-0 flex-1 flex-col gap-2.5">
                  <Bar size={8} className="w-32" />
                  {/* The title and its status chip wrap on a phone, as the card does. */}
                  <span className="flex flex-wrap items-center gap-2">
                    <Bar size={14} className="w-44 max-w-full" />
                    <Pill className="h-6 w-20" />
                  </span>
                  <Bar size={10} className="w-full" />
                  <Bar size={10} className="w-1/3" />
                  <Bar size={8} className="w-32" />
                </span>
              </div>
            ))}
          </div>
        </SkeletonRegion>
      </BrowseLayout>
    </>
  );
}
