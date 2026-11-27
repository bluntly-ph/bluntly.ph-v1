import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";
import { Bar, Block } from "@/components/ui/Skeleton";

export default function Loading() {
  return (
    <>
      <div className="hidden md:block">
        <SiteHeaderSkeleton />
      </div>
      <div className="mx-auto w-full max-w-[72rem] px-6 py-8 lg:px-10 lg:py-10">
        <Bar size={18} className="my-[5px] w-44" />
        <div
          role="status"
          aria-busy="true"
          aria-live="polite"
          className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4"
        >
          <span className="sr-only">Loading categories</span>
          {Array.from({ length: 14 }, (_, i) => (
            <Block className="h-24 w-full" key={i} />
          ))}
        </div>
      </div>
    </>
  );
}
