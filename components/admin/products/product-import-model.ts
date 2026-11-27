/**
 * The product CSV import's rules for the modal (POST /admin/products/import):
 * what each row's outcome reads as, which rows can be attached to the product
 * they match, what the Import button says, and the result summary. Pure, so
 * tests/frontend/product-import-model.test.mjs can hold it.
 */

export type Outcome = "new" | "exists" | "duplicate" | "conflict" | "error" | "created" | "attached" | "failed";
export type Tone = "success" | "muted" | "warning" | "critical" | "neutral";

export type ImportRow = {
  line: number;
  outcome: Outcome;
  name: string | null;
  category: string | null;
  errors: string[];
  product_id: string | null;
  existing_name: string | null;
  duplicate_of_line: number | null;
  matched_by: string | null;
  attach_adds: string[];
};

export type ImportResult = {
  applied: boolean;
  rows: ImportRow[];
  counts: Record<string, number>;
  columns: string[];
  required: string[];
  ignored_columns: string[];
  failure: string | null;
};

export const OUTCOME: Record<Outcome, { label: string; tone: Tone }> = {
  new: { label: "New", tone: "success" },
  created: { label: "Added", tone: "success" },
  exists: { label: "Matches a product", tone: "muted" },
  attached: { label: "Attached", tone: "success" },
  duplicate: { label: "Repeated in file", tone: "warning" },
  conflict: { label: "Conflict", tone: "critical" },
  error: { label: "Can't import", tone: "critical" },
  failed: { label: "Failed", tone: "critical" },
};

/** A matched row the admin may attach: it adds a listing or an alias. */
export function canAttach(row: ImportRow): boolean {
  return row.outcome === "exists" && row.attach_adds.length > 0;
}

/** The lines asked to attach that the current preview still allows. */
export function attachLines(rows: ImportRow[], chosen: ReadonlySet<number>): number[] {
  return rows.filter((r) => canAttach(r) && chosen.has(r.line)).map((r) => r.line);
}

/** The sentence under a row's name: why it is what it is. */
export function rowNote(row: ImportRow): string | null {
  switch (row.outcome) {
    case "error":
    case "conflict":
    case "failed":
      return row.errors.join(" ") || null;
    case "exists":
    case "attached":
      return `Matches “${row.existing_name ?? "a product"}” by ${row.matched_by ?? "name"}`;
    case "duplicate":
      return `Same as row ${row.duplicate_of_line}`;
    default:
      return null;
  }
}

/** The Import button: what applying will do, or why it can't. */
export function importLabel(newCount: number, attachCount: number): string {
  if (!newCount && !attachCount) return "Nothing to import";
  const parts = [];
  if (newCount) parts.push(`Import ${newCount} new`);
  if (attachCount) parts.push(`${parts.length ? "attach" : "Attach"} ${attachCount}`);
  return parts.join(" · ");
}

/** The result's chips, in reading order; zero counts (but Total) are left out. */
export function summaryChips(result: Pick<ImportResult, "applied" | "counts">): { label: string; tone: Tone }[] {
  const c = result.counts;
  const n = (k: string) => c[k] ?? 0;
  const chips: { label: string; tone: Tone }[] = [{ label: `${n("total")} rows`, tone: "neutral" }];
  const add = (count: number, label: string, tone: Tone) => {
    if (count) chips.push({ label: `${count} ${label}`, tone });
  };
  if (result.applied) {
    add(n("imported"), "added", "success");
    add(n("attached"), "attached", "success");
  } else {
    add(n("new"), "new", "success");
    add(n("exists"), "match a product", "muted");
  }
  if (result.applied) add(n("skipped"), "skipped", "muted");
  else {
    add(n("duplicate"), "repeated", "warning");
    add(n("conflict"), "conflict", "critical");
  }
  add(n("invalid"), "can't import", "critical");
  add(n("failed"), "failed", "critical");
  return chips;
}
