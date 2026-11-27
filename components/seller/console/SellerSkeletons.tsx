import {
  Bar,
  Block,
  Circle,
  type ColumnSpec,
  IconButtonsSkeleton,
  MetricRowSkeleton,
  PaginationSkeleton,
  Pill,
  SegmentedSkeleton,
  SkeletonRegion,
  TableSkeleton,
} from "@/components/ui/Skeleton";

/**
 * Screen/Seller/{Overview,Reviews,Questions,Appeals,Settings,Sellerrules}/Loading (Figma
 * 8228:24472, 8228:25327, 8228:25961, 8228:26321, 8228:28761, 8228:28562): the shapes of
 * each screen's content while its data loads. Inside a store the rail is real
 * and stays put (the console layout renders it); only the working area turns
 * into placeholders. `SellerConsoleSkeleton` adds the rail for the first entry
 * into the console, before the layout itself has its data.
 */

const CARD = "rounded-[16px] border border-[var(--border-subtle)] p-5";

function StatCards({ count }: { count: number }) {
  return <MetricRowSkeleton count={count} className={count === 4 ? "gap-3 sm:grid-cols-2 xl:grid-cols-4" : "gap-3 sm:grid-cols-3"} />;
}

export type SellerListSpec = {
  label: string;
  /** The screen's own 24 px title, as wide as its word. */
  title: string;
  tabs: number;
  icons: number;
  columns: ColumnSpec[];
  minWidth: number;
};

const col = (kind: ColumnSpec["kind"], track?: string): ColumnSpec => ({ kind, track });

/** The list screens: title, view tabs + sort/filter/search, three figures, the table (columns as the real ones), the pager. */
export const SELLER_LISTS = {
  reviews: {
    label: "Loading reviews", title: "w-28", tabs: 3, icons: 3, minWidth: 960,
    columns: [col("avatar", "minmax(0,1.3fr)"), col("figure", "90px"), col("lines", "minmax(0,2.2fr)"),
      col("text"), col("text", "110px"), col("action")],
  },
  questions: {
    label: "Loading questions", title: "w-32", tabs: 3, icons: 3, minWidth: 860,
    columns: [col("lines", "minmax(0,2.4fr)"), col("text", "110px"), col("figure", "90px"),
      col("figure", "90px"), col("action")],
  },
  appeals: {
    label: "Loading appeals", title: "w-28", tabs: 3, icons: 2, minWidth: 900,
    columns: [col("lines", "minmax(0,1.8fr)"), col("lines"), col("chip"), col("text", "110px"),
      col("action")],
  },
  products: {
    label: "Loading products", title: "w-32", tabs: 3, icons: 3, minWidth: 900,
    columns: [col("thumb", "minmax(0,1.8fr)"), col("figure", "80px"), col("figure", "80px"),
      col("text"), col("text"), col("figure", "90px"), col("action")],
  },
} satisfies Record<string, SellerListSpec>;

export function SellerListSkeleton({ spec }: { spec: SellerListSpec }) {
  return (
    <SkeletonRegion label={spec.label} className="flex flex-col gap-4">
      <Bar size={18} className={`my-[3px] ${spec.title}`} />
      <div className="flex flex-wrap items-center gap-2">
        <SegmentedSkeleton count={spec.tabs} />
        <span className="flex-1" />
        <IconButtonsSkeleton count={spec.icons} />
      </div>
      <StatCards count={3} />
      <TableSkeleton columns={spec.columns} minWidth={spec.minWidth} rows={10} />
      <PaginationSkeleton />
    </SkeletonRegion>
  );
}

/** A product's analytics: its name and period, four figures, the trend beside the verdicts, two breakdowns. */
export function SellerProductSkeleton() {
  return (
    <SkeletonRegion label="Loading this product" className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Bar size={18} className="my-[3px] w-72 max-w-full" />
        <span className="flex-1" />
        <Pill className="h-8 w-28" />
      </div>
      <StatCards count={4} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className={CARD}>
          <Bar size={14} className="w-32" />
          <Bar size={8} className="mt-2 w-56" />
          <Block className="mt-5 h-[170px] w-full" />
        </div>
        <div className={`${CARD} flex flex-col gap-4`}>
          <Bar size={14} className="w-24" />
          <Bar size={8} className="w-full" />
          {Array.from({ length: 3 }, (_, i) => (
            <span key={i} className="flex items-center gap-3 py-1.5">
              <Circle size={8} />
              <span className="flex flex-1 flex-col gap-2">
                <Bar size={10} className="w-24" />
                <Bar size={8} className="w-16" />
              </span>
              <Bar size={10} className="w-10" />
            </span>
          ))}
        </div>
      </div>
      <div className={CARD}>
        <Bar size={14} className="w-56" />
        <Bar size={8} className="mt-2 w-72 max-w-full" />
        <Bar size={10} className="mt-5 w-64 max-w-full" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {[0, 1].map((c) => (
          <div key={c} className={`${CARD} flex flex-col gap-3`}>
            <Bar size={14} className="w-40" />
            {Array.from({ length: 4 }, (_, i) => (
              <span key={i} className="flex flex-col gap-2">
                <Bar size={10} className="w-3/5" />
                <Bar size={8} className="w-full" />
              </span>
            ))}
          </div>
        ))}
      </div>
    </SkeletonRegion>
  );
}

/** Overview: greeting, four figures, waiting list + rating, months + notes, latest reviews. */
export function SellerOverviewSkeleton() {
  return (
    <SkeletonRegion label="Loading your store" className="flex flex-col gap-4">
      <div className="flex items-center">
        <Bar size={18} className="w-56" />
        <span className="flex-1" />
        <Pill className="h-8 w-28" />
      </div>
      <StatCards count={4} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className={CARD}>
          <Bar size={14} className="w-28" />
          <Bar size={10} className="mt-2 w-56" />
          <div className="mt-4 flex flex-col">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-3 first:border-t-0">
                <Circle size={28} />
                <span className="flex flex-1 flex-col gap-1.5">
                  <Bar size={10} className="w-2/5" />
                  <Bar size={10} className="w-3/5" />
                </span>
                <Pill className="h-8 w-16" />
              </div>
            ))}
          </div>
        </div>
        <div className={CARD}>
          <Bar size={14} className="w-24" />
          <Bar size={10} className="mt-2 w-36" />
          <Bar size={18} className="mt-5 w-40" />
          <div className="mt-5 flex flex-col gap-3">
            {Array.from({ length: 5 }, (_, i) => (
              <Bar size={8} className="w-full" key={i} />
            ))}
          </div>
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className={CARD}>
          <Bar size={14} className="w-24" />
          <Bar size={10} className="mt-2 w-48" />
          <div className="mt-6 flex h-28 items-end gap-3">
            {[40, 55, 45, 65, 75, 100].map((h, i) => (
              <Block className="flex-1" key={i} style={{ height: `${h}%` }} />
            ))}
          </div>
        </div>
        <div className={`${CARD} flex flex-col gap-4`}>
          <Bar size={14} className="w-24" />
          {Array.from({ length: 3 }, (_, i) => (
            <span key={i} className="flex flex-col gap-1.5">
              <Bar size={10} className="w-3/5" />
              <Bar size={8} className="w-full" />
            </span>
          ))}
        </div>
      </div>
      <Bar size={14} className="w-28" />
      <TableSkeleton columns={SELLER_LISTS.reviews.columns} minWidth={960} rows={5} />
    </SkeletonRegion>
  );
}

/** Settings: Notifications (seven switches) and Account beside Need help and Give up this store. */
export function SellerSettingsSkeleton() {
  return (
    <SkeletonRegion label="Loading settings" className="flex flex-col gap-4">
      <Bar size={18} className="my-[3px] w-28" />
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,614px)_minmax(0,360px)]">
        <div className="flex flex-col gap-4">
          <div className={CARD}>
            <Bar size={14} className="w-28" />
            <Bar size={8} className="mt-2 w-48" />
            <div className="mt-3 flex flex-col">
              {Array.from({ length: 7 }, (_, i) => (
                <div key={i} className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-[19px]">
                  <span className="flex flex-1 flex-col gap-3">
                    <Bar size={10} className="w-36" />
                    <Bar size={8} className="w-48" />
                  </span>
                  <Pill className="h-5 w-9" />
                </div>
              ))}
            </div>
          </div>
          <div className={CARD}>
            <Bar size={14} className="w-20" />
            <div className="mt-4 flex flex-col gap-3">
              {Array.from({ length: 3 }, (_, i) => (
                <span key={i} className="flex gap-4">
                  <Bar size={10} className="w-24" />
                  <Bar size={10} className="w-32" />
                </span>
              ))}
            </div>
            <Pill className="mt-4 h-9 w-36" />
          </div>
        </div>
        <div className="flex flex-col gap-4">
          {[2, 4].map((lines, c) => (
            <div key={c} className={CARD}>
              <Bar size={14} className="w-28" />
              <div className="mt-3 flex flex-col gap-2">
                {Array.from({ length: lines }, (_, i) => (
                  <Bar key={i} size={10} className={i === lines - 1 ? "w-2/5" : "w-full"} />
                ))}
              </div>
              <Pill className="mt-4 h-9 w-36" />
            </div>
          ))}
        </div>
      </div>
    </SkeletonRegion>
  );
}

/** First entry into the console: the 232px rail, then the Overview's shape. */
export function SellerConsoleSkeleton() {
  return (
    <div className="flex h-dvh overflow-hidden bg-[var(--surface-app)] p-2 lg:pl-0">
      <aside aria-hidden className="hidden w-[232px] shrink-0 flex-col gap-5 px-3 py-2 lg:flex">
        <div className="flex items-center gap-2">
          <Block className="size-8" />
          <span className="flex flex-col gap-1.5">
            <Bar size={10} className="w-24" />
            <Bar size={10} className="w-20" />
          </span>
        </div>
        <Block className="h-9 w-full" />
        {[1, 3, 3].map((n, g) => (
          <div key={g} className="flex flex-col gap-2">
            {g ? <Bar size={10} className="w-12" /> : null}
            {Array.from({ length: n }, (_, i) => (
              <Block className="h-7 w-full" key={i} />
            ))}
          </div>
        ))}
        <div className="mt-auto flex flex-col gap-2">
          {Array.from({ length: 3 }, (_, i) => (
            <Block className="h-7 w-full" key={i} />
          ))}
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)]">
        <div className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--border-subtle)] pl-6 pr-4">
          <Bar size={10} className="w-40" />
          <span className="flex-1" />
          <Circle size={36} />
        </div>
        <div className="min-h-0 flex-1 overflow-hidden px-4 pb-6 pt-5 sm:px-6">
          <SellerOverviewSkeleton />
        </div>
      </div>
    </div>
  );
}

/** Seller rules: the title, the "On this page" list and paragraphs. */
export function SellerRulesSkeleton() {
  return (
    <SkeletonRegion label="Loading the seller rules" className="flex max-w-[760px] flex-col gap-4">
      <Bar size={18} className="w-36" />
      <Bar size={10} className="w-3/5" />
      <div className={`${CARD} flex flex-col gap-2`}>
        {Array.from({ length: 5 }, (_, i) => (
          <Bar size={10} className="w-40" key={i} />
        ))}
      </div>
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="flex flex-col gap-2">
          <Bar size={14} className="w-48" />
          <Bar size={10} className="w-full" />
          <Bar size={10} className="w-11/12" />
          <Bar size={10} className="w-2/3" />
        </div>
      ))}
    </SkeletonRegion>
  );
}

/** Messages (Screen/Seller/Inbox/Loading 8314:32250): tabs, the list, the thread. */
export function SellerMessagesSkeleton() {
  return (
    <SkeletonRegion label="Loading messages" className="flex h-full min-h-[520px] flex-col gap-4">
      <Bar size={18} className="w-32" />
      <div className="flex items-center">
        <Block className="h-8 w-40" />
        <span className="flex-1" />
        <Pill className="h-9 w-32" />
      </div>
      <div className="flex min-h-0 flex-1 overflow-hidden rounded-[16px] border border-[var(--border-subtle)]">
        <div className="flex w-full flex-col gap-1 p-2 lg:w-[340px] lg:border-r lg:border-[var(--border-subtle)]">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="flex gap-3 px-3 py-3">
              <Circle size={32} />
              <span className="flex flex-1 flex-col gap-2">
                <Bar size={10} className="w-3/5" />
                <Bar size={10} className="w-4/5" />
              </span>
            </div>
          ))}
        </div>
        <div className="hidden flex-1 flex-col lg:flex">
          <div className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-5 py-3">
            <Circle size={32} />
            <span className="flex flex-1 flex-col gap-2">
              <Bar size={10} className="w-28" />
              <Bar size={10} className="w-52" />
            </span>
            <Pill className="h-6 w-14" />
          </div>
          <div className="flex flex-1 flex-col gap-4 px-5 py-4">
            <Block className="h-16 ml-auto w-2/5" />
            <Block className="h-20 w-2/5" />
          </div>
          <div className="border-t border-[var(--border-subtle)] px-5 py-4">
            <Block className="h-11 w-full" />
          </div>
        </div>
      </div>
    </SkeletonRegion>
  );
}

/** Insights (Screen/Seller/Insights/Loading 8228:27172): figures, sparklines, themes, replies, peers. */
export function SellerInsightsSkeleton() {
  return (
    <SkeletonRegion label="Loading insights" className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Bar size={18} className="w-28" />
        <span className="flex-1" />
        <Pill className="h-9 w-36" />
        <Pill className="h-9 w-28" />
        <Pill className="h-9 w-32" />
      </div>
      <StatCards count={4} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className={`${CARD} flex flex-col gap-3`}>
            <Bar size={10} className="w-24" />
            <span className="flex gap-2">
              <Bar size={18} className="w-12" />
              <Bar size={10} className="w-12 self-end" />
            </span>
            <Block className="mt-1 h-14 w-full" />
            <span className="flex justify-between">
              <Bar size={10} className="w-6" />
              <Bar size={10} className="w-6" />
            </span>
          </div>
        ))}
      </div>
      <div className={CARD}>
        <Bar size={14} className="w-56" />
        <Bar size={10} className="mt-2 w-80 max-w-full" />
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          {[0, 1].map((c) => (
            <div key={c} className="flex flex-col gap-4">
              <Bar size={10} className="w-16" />
              {Array.from({ length: 3 }, (_, i) => (
                <span key={i} className="flex flex-col gap-1.5">
                  <Bar size={10} className="w-2/5" />
                  <Bar size={8} className="w-full" />
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className={CARD}>
          <Bar size={14} className="w-40" />
          <Bar size={10} className="mt-2 w-56" />
          <div className="mt-6 flex h-32 items-end gap-3">
            {[60, 68, 72, 80, 84, 90].map((h, i) => (
              <Block className="flex-1" key={i} style={{ height: `${h}%` }} />
            ))}
          </div>
          <Bar size={10} className="mt-6 w-full" />
        </div>
        <div className={`${CARD} flex flex-col gap-5`}>
          <Bar size={14} className="w-48" />
          {Array.from({ length: 4 }, (_, i) => (
            <span key={i} className="flex flex-col gap-2">
              <Bar size={10} className="w-2/5" />
              <Bar size={8} className="w-full" />
            </span>
          ))}
        </div>
      </div>
      <Bar size={10} className="w-80 max-w-full" />
    </SkeletonRegion>
  );
}

function Rows({ rows }: { rows: number }) {
  return (
    <div className="mt-4 flex flex-col">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-6 border-t border-[var(--border-subtle)] py-3">
          <Bar size={10} className="w-28" />
          <Bar size={10} className="w-32" />
        </div>
      ))}
    </div>
  );
}

/** Store profile (Screen/Seller/StoreProfile/Loading 8228:27673): store card, ownership, rules, stores. */
export function SellerProfileSkeleton() {
  return (
    <SkeletonRegion label="Loading the store profile" className="flex flex-col gap-4">
      <div className="flex items-center">
        <Bar size={18} className="w-36" />
        <span className="flex-1" />
        <Pill className="h-9 w-36" />
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex flex-col gap-4">
          <div className={CARD}>
            <div className="flex items-center gap-3">
              <Block className="size-14" />
              <span className="flex flex-1 flex-col gap-2">
                <Bar size={14} className="w-48" />
                <Bar size={10} className="w-40" />
              </span>
              <Pill className="h-8 w-32" />
            </div>
            <Rows rows={4} />
            <Block className="h-10 mt-2 w-full" />
          </div>
          <div className={CARD}>
            <Bar size={14} className="w-24" />
            <Bar size={10} className="mt-2 w-32" />
            <Rows rows={5} />
            <Block className="h-10 mt-2 w-full" />
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <div className={`${CARD} flex flex-col gap-3`}>
            <Bar size={14} className="w-48" />
            {Array.from({ length: 7 }, (_, i) => (
              <Bar size={10} className="w-4/5" key={i} />
            ))}
          </div>
          <div className={`${CARD} flex flex-col gap-3`}>
            <Bar size={14} className="w-24" />
            {Array.from({ length: 2 }, (_, i) => (
              <span key={i} className="flex items-center gap-3">
                <Block className="size-7" />
                <Bar size={10} className="flex-1" />
              </span>
            ))}
            <Pill className="h-8 w-36" />
          </div>
        </div>
      </div>
    </SkeletonRegion>
  );
}

/** Public page (Screen/Seller/PublicPage/Loading 8228:28024): the note, the store, reviews, ratings, questions. */
export function SellerPublicSkeleton() {
  return (
    <SkeletonRegion label="Loading your public page" className="flex flex-col gap-4">
      <div className="flex items-center">
        <Bar size={18} className="w-32" />
        <span className="flex-1" />
        <Pill className="h-9 w-32" />
      </div>
      <Block className="h-11 w-full" />
      <div className={CARD}>
        <div className="flex items-center gap-3">
          <Block className="size-14" />
          <span className="flex flex-col gap-2">
            <Bar size={14} className="w-48" />
            <Bar size={10} className="w-40" />
          </span>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-4 border-t border-[var(--border-subtle)] pt-4 md:grid-cols-6">
          {Array.from({ length: 6 }, (_, i) => (
            <span key={i} className="flex flex-col gap-2">
              <Bar size={10} className="w-16" />
              <Bar size={14} className="w-10" />
            </span>
          ))}
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Bar size={14} className="w-28" />
            <span className="flex-1" />
            <Pill className="h-8 w-28" />
            <Pill className="h-8 w-20" />
          </div>
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className={`${CARD} flex flex-col gap-3`}>
              <span className="flex items-center gap-2">
                <Circle size={28} />
                <Bar size={10} className="w-24" />
                <span className="flex-1" />
                <Bar size={10} className="w-24" />
              </span>
              <Bar size={10} className="w-4/5" />
              <Bar size={10} className="w-3/5" />
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-4">
          <div className={`${CARD} flex flex-col gap-3`}>
            <Bar size={14} className="w-20" />
            {Array.from({ length: 5 }, (_, i) => (
              <Bar size={8} className="w-full" key={i} />
            ))}
          </div>
          <div className={`${CARD} flex flex-col gap-3`}>
            <Bar size={14} className="w-44" />
            <Bar size={10} className="w-4/5" />
            <Bar size={10} className="w-3/5" />
          </div>
        </div>
      </div>
    </SkeletonRegion>
  );
}
