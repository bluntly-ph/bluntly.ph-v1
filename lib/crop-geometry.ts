/**
 * The arithmetic behind the photo croppers (profile photo, review photo;
 * QA-062). Pure, so the part that decides what is saved is tested without a
 * DOM: a crop that leaves an empty edge, zooms around the wrong point or reads
 * the wrong source rectangle looks fine in a screenshot and wrong in the file.
 *
 * Coordinates: the photo is drawn at `scale` (CSS px per image px) with its
 * top-left corner at `offset` inside a square window `view` CSS px wide.
 */

export type Size = { w: number; h: number };
export type Offset = { x: number; y: number };

/** The scale at which the photo's SHORT side exactly fills the window. */
export function coverScale(view: number, natural: Size): number {
  return view / Math.min(natural.w, natural.h);
}

/** Keep the photo covering the whole window: no empty edge is ever saved. */
export function clampOffset(o: Offset, natural: Size, scale: number, view: number): Offset {
  const minX = view - natural.w * scale;
  const minY = view - natural.h * scale;
  return {
    x: Math.min(0, Math.max(minX, o.x)),
    y: Math.min(0, Math.max(minY, o.y)),
  };
}

/** The photo centred in the window at `scale`. */
export function centred(natural: Size, scale: number, view: number): Offset {
  return { x: (view - natural.w * scale) / 2, y: (view - natural.h * scale) / 2 };
}

/**
 * Change the scale keeping the image point under `anchor` (window px) still —
 * the window's centre for the slider and keys, the fingers' midpoint for a
 * pinch. Clamped, so zooming out never uncovers an edge.
 */
export function zoomAround(
  offset: Offset,
  from: number,
  to: number,
  anchor: Offset,
  natural: Size,
  view: number,
): Offset {
  const ix = (anchor.x - offset.x) / from;
  const iy = (anchor.y - offset.y) / from;
  return clampOffset({ x: anchor.x - ix * to, y: anchor.y - iy * to }, natural, to, view);
}

/** The square of the ORIGINAL image the window shows: what gets saved. */
export function sourceSquare(offset: Offset, scale: number, view: number): { sx: number; sy: number; side: number } {
  return { sx: -offset.x / scale, sy: -offset.y / scale, side: view / scale };
}

/**
 * The saved image's side in pixels. A fixed size when asked (the avatar is
 * always 512), otherwise the crop's own resolution capped at `max` — never
 * upscaled, so a small photo is not blown up into a blurry large file.
 */
export function outputSide(sourceSide: number, max: number, fixed = false): number {
  if (fixed) return max;
  return Math.max(1, Math.min(max, Math.round(sourceSide)));
}
