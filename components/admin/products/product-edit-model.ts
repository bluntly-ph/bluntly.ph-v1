/**
 * The Edit product / Add to catalogue modals' name builder (Figma 7970:11204,
 * 7970:11467). Pure; tested in tests/frontend/product-edit-model.test.mjs.
 *
 * A name part is one of the three the catalogue stores (products.line,
 * key_spec, descriptor); each kind once. "Saves as" is composed exactly as the
 * API composes canonical_name: brand, line, variant, type, then every spec
 * switched "In name".
 */

export type PartKind = "line" | "variant" | "type";
export const PART_LABEL: Record<PartKind, string> = { line: "Line", variant: "Variant", type: "Type" };
export const PART_KINDS: PartKind[] = ["line", "variant", "type"];

export type NamePart = { kind: PartKind; value: string };
export type SpecRow = { label: string; value: string; in_name: boolean };

const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();

export function savesAs(brand: string, parts: NamePart[], specs: SpecRow[]): string {
  const of = (k: PartKind) => clean(parts.find((p) => p.kind === k)?.value);
  return [clean(brand), of("line"), of("variant"), of("type"), ...specs.filter((s) => s.in_name).map((s) => clean(s.value))]
    .filter(Boolean)
    .join(" ");
}

/** The parts as the API's canonicalize body takes them. */
export function partsPayload(parts: NamePart[]): { product_line: string; key_spec: string | null; descriptor: string | null } {
  const of = (k: PartKind) => clean(parts.find((p) => p.kind === k)?.value) || null;
  return { product_line: of("line") ?? "", key_spec: of("variant"), descriptor: of("type") };
}

/** A product's stored parts back as rows (Line always first). */
export function partsFrom(p: {
  line?: string | null;
  key_spec?: string | null;
  descriptor?: string | null;
  canonical_name?: string | null;
  brand?: string | null;
}): NamePart[] {
  // Products named before the parts were stored (0071) have only the whole
  // name: the line is that name without its brand, to be split by hand.
  let line = p.line ?? "";
  if (!line && p.canonical_name) {
    const brand = clean(p.brand);
    const whole = clean(p.canonical_name);
    line = brand && whole.toLowerCase().startsWith(`${brand.toLowerCase()} `) ? whole.slice(brand.length + 1) : whole;
  }
  const rows: NamePart[] = [{ kind: "line", value: line }];
  if (p.key_spec) rows.push({ kind: "variant", value: p.key_spec });
  if (p.descriptor) rows.push({ kind: "type", value: p.descriptor });
  return rows;
}

/** Specs with a label and a value; blanks (the frame's "Optional") are dropped. */
export function specsPayload(specs: SpecRow[]): SpecRow[] {
  return specs
    .map((s) => ({ label: clean(s.label), value: clean(s.value), in_name: s.in_name }))
    .filter((s) => s.label && s.value);
}

/** What is still missing before the modal can save. */
export function blocker(brand: string, parts: NamePart[], category: string | null): string | null {
  if (!clean(brand)) return "Add the brand.";
  if (!partsPayload(parts).product_line) return "Add the product line.";
  if (!category) return "Choose a category.";
  return null;
}

/**
 * "As is" (Overlay/Product/Edit · As is, Figma 8277:29379): the name saved
 * exactly as typed, for a product with no brand, line or model. A product
 * already stored without brand and line reopens in this mode.
 */
export function startsAsIs(p: { brand?: string | null; line?: string | null; canonical_name?: string | null }): boolean {
  return !clean(p.brand) && !clean(p.line) && !!clean(p.canonical_name);
}

export function asIsBlocker(name: string, category: string | null): string | null {
  if (clean(name).length < 2) return "Type the name.";
  if (!category) return "Choose a category.";
  return null;
}

/** The canonicalize / create body's naming fields for an as-is name. */
export function asIsPayload(name: string, brand: string, noBrand: boolean) {
  return { name_as_is: clean(name), brand: noBrand ? "" : clean(brand), product_line: "", key_spec: null, descriptor: null };
}
