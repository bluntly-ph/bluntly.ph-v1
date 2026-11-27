/**
 * Skeleton primitives: what a screen draws while a server component awaits its
 * data.
 *
 * These exist because the backend is not fast: Supabase is in Singapore and a
 * cold DB-backed call measured 1.7-2.9s (see vercel.json). Without a fallback,
 * that is 1.7-2.9s of blank page with nothing to say the app is working.
 *
 * One visual language (Figma "Skeleton / Bar" and "Skeleton / Block"):
 *
 * - fill `--skeleton-fill`, the opaque #e6e6e6 of Figma border/subtle;
 * - `Bar` — text: 8, 10, 14 or 18 px high, fully rounded (8 a meta line, 10
 *   body text, 14 a label or emphasised line, 18 a title or a figure);
 * - `Block` — a 12 px-radius surface: thumbnail, field, chart, image;
 * - `Pill` — a fully rounded control: button, chip, tab, page switcher;
 * - `Circle` — an avatar or an icon.
 *
 * Nothing else: no other fill, radius or height. A placeholder stands where the
 * real thing will be, with its width and height, so the screen does not jump
 * when the data arrives. Placeholders are `aria-hidden` and never focusable;
 * the region around them (`SkeletonRegion`) says "loading" once to a screen
 * reader. The pulse stops under prefers-reduced-motion.
 */

import type { CSSProperties, ReactNode } from "react";

export type BarSize = 8 | 10 | 14 | 18;

const BAR_HEIGHT: Record<BarSize, string> = {
  8: "h-2",
  10: "h-2.5",
  14: "h-3.5",
  18: "h-[18px]",
};

const FILL = "block shrink-0 animate-pulse bg-[var(--skeleton-fill)] motion-reduce:animate-none";

type Shape = { className?: string; style?: CSSProperties };

/** A line of text. Width from `className` (w-24, w-3/5, …). */
export function Bar({ size = 10, className = "", style }: Shape & { size?: BarSize }) {
  return <span aria-hidden="true" style={style} className={`${FILL} rounded-full ${BAR_HEIGHT[size]} ${className}`} />;
}

/** A 12 px-radius surface. Size from `className` (h-11 w-full, aspect-square, …). */
export function Block({ className = "", style }: Shape) {
  return <span aria-hidden="true" style={style} className={`${FILL} rounded-[12px] ${className}`} />;
}

/** A fully rounded control: a button (h-9), a chip (h-6), a tab, a pager. */
export function Pill({ className = "", style }: Shape) {
  return <span aria-hidden="true" style={style} className={`${FILL} rounded-full ${className}`} />;
}

/** An avatar or an icon, `size` px square. */
export function Circle({ size = 32, className = "" }: { size?: number; className?: string }) {
  return <span aria-hidden="true" style={{ width: size, height: size }} className={`${FILL} rounded-full ${className}`} />;
}

/**
 * The loading region: announced once ("Loading the queue"), then silent.
 * `aria-busy` with a polite live region rather than silence, so a screen
 * reader user hears that the page is working instead of nothing.
 */
export function SkeletonRegion({ label, className = "", children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <div role="status" aria-busy="true" aria-live="polite" className={className}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

/**
 * The console's segmented control: a 30 px track of ~90 px tabs. The tabs are
 * invisible spacers inside the filled track, so on a phone it wraps onto a
 * second row exactly where the real one does.
 */
export function SegmentedSkeleton({ count, className = "" }: { count: number; className?: string }) {
  return (
    <span aria-hidden="true" className={`flex w-fit max-w-full flex-wrap gap-[2px] rounded-[12px] bg-[var(--skeleton-fill)] p-[3px] motion-safe:animate-pulse ${className}`}>
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className="h-6 w-[86px]" />
      ))}
    </span>
  );
}

/** Sort / filter / search: 32 px icon buttons, round or square (12 px here). */
export function IconButtonsSkeleton({ count, round = false }: { count: number; round?: boolean }) {
  return (
    <span className="flex items-center gap-1">
      {Array.from({ length: count }, (_, i) => (round ? <Circle key={i} size={32} /> : <Block key={i} className="size-8" />))}
    </span>
  );
}

/** A figure card: label, value, note. The console's 16 px card with a hairline. */
function MetricCardSkeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`flex flex-col gap-3.5 rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-5 ${className}`}>
      <Bar size={10} className="w-24" />
      <Bar size={18} className="my-1.5 w-28" />
      <Bar size={10} className="w-40 max-w-full" />
    </div>
  );
}

/** A row of figure cards, as the screen lays them out. */
export function MetricRowSkeleton({ count, className = "gap-4 md:grid-cols-3" }: { count: number; className?: string }) {
  return (
    <div className={`grid ${className}`}>
      {Array.from({ length: count }, (_, i) => (
        <MetricCardSkeleton key={i} />
      ))}
    </div>
  );
}

/**
 * One column of a table placeholder.
 *  - `kind`: `text` one line · `lines` a title and a meta line · `avatar` a
 *    person (circle + two lines) · `thumb` a product or store (block + two
 *    lines) · `chip` a status chip · `action` a button · `figure` a short number
 *  - `track`: the column's CSS grid track, as wide as the real column
 *    ("31%", "120px", "minmax(0,2fr)"); default an equal share
 */
export type ColumnSpec = {
  kind: "text" | "lines" | "avatar" | "thumb" | "chip" | "action" | "figure";
  track?: string;
};

function Cell({ kind }: { kind: ColumnSpec["kind"] }) {
  switch (kind) {
    case "avatar":
    case "thumb":
      return (
        <span className="flex min-w-0 items-center gap-3 px-3">
          {kind === "avatar" ? <Circle size={28} /> : <Block className="size-8" />}
          <span className="flex min-w-0 flex-1 flex-col gap-1.5">
            <Bar size={10} className="w-4/5" />
            <Bar size={8} className="w-1/2" />
          </span>
        </span>
      );
    case "lines":
      return (
        <span className="flex min-w-0 flex-col gap-1.5 px-3">
          <Bar size={10} className="w-4/5" />
          <Bar size={8} className="w-1/2" />
        </span>
      );
    case "chip":
      return (
        <span className="flex min-w-0 px-3">
          <Pill className="h-6 w-20" />
        </span>
      );
    case "action":
      return (
        <span className="flex min-w-0 justify-end px-3">
          <Pill className="h-8 w-16" />
        </span>
      );
    case "figure":
      return (
        <span className="flex min-w-0 px-3">
          <Bar size={10} className="w-10" />
        </span>
      );
    default:
      return (
        <span className="flex min-w-0 px-3">
          <Bar size={10} className="w-3/4" />
        </span>
      );
  }
}

/**
 * A console table (Admin and Seller "TBL"): the 16 px card, a 40 px header
 * strip, rows of about 52 px, cells padded 12 px. `minWidth` is the real
 * table's: below it the real one scrolls sideways, so the placeholder keeps its
 * columns and is clipped rather than squeezed.
 */
export function TableSkeleton({ columns, rows = 8, minWidth = 900, className = "" }: {
  columns: ColumnSpec[];
  rows?: number;
  minWidth?: number;
  className?: string;
}) {
  const grid: CSSProperties = {
    display: "grid",
    gridTemplateColumns: columns.map((c) => c.track ?? "minmax(0,1fr)").join(" "),
    minWidth,
  };
  return (
    <div className={`overflow-hidden rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] ${className}`}>
      <div style={grid} className="h-10 items-center bg-[var(--surface-app)]">
        {columns.map((col, i) => (
          <span key={i} className={`flex px-3 ${col.kind === "action" ? "justify-end" : ""}`}>
            <Bar size={8} className="w-14" />
          </span>
        ))}
      </div>
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} style={grid} className="h-[52px] items-center border-t border-[var(--border-subtle)]">
          {columns.map((col, i) => (
            <Cell key={i} kind={col.kind} />
          ))}
        </div>
      ))}
    </div>
  );
}

/** The console pager: "Showing 1–10 of 240", then the page cells and the page size. */
export function PaginationSkeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <Bar size={10} className="mr-auto w-36" />
      <Pill className="h-[30px] w-40" />
      <Pill className="h-[26px] w-24" />
    </div>
  );
}
