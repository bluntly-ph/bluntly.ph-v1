"use client";

import { useMemo, useRef, useState } from "react";

import {
  centred,
  clampOffset,
  coverScale,
  outputSide,
  sourceSquare,
  zoomAround,
  type Offset,
  type Size,
} from "@/lib/crop-geometry";

const MAX_ZOOM = 3;

/**
 * Position and crop a chosen photo BEFORE anything is uploaded (QA-062; the
 * profile photo's cropper, QA-019/040, generalised).
 *
 * Drag with a mouse or one finger to reposition, pinch with two fingers or use
 * the slider (or +/−) to zoom, arrow keys to nudge. The window is exactly what
 * is saved — a square for a review photo, the circle inscribed in it for an
 * avatar — and only that crop leaves the browser; the file as picked is never
 * sent. A photo this browser cannot decode (HEIC outside Safari) cannot be
 * previewed or positioned, so it is refused with a way forward rather than
 * uploaded blind.
 */
export function ImageCropper({
  file,
  onDone,
  onCancel,
  shape = "square",
  view = 240,
  maxOut = 1600,
  fixedOut = false,
  label,
  doneLabel = "Use photo",
  suffix = "-crop",
}: {
  file: File;
  onDone: (result: { file: File } | { error: string }) => void;
  onCancel: () => void;
  shape?: "square" | "circle";
  /** The on-screen window, in CSS pixels. */
  view?: number;
  /** The saved image's side: the cap, or exactly this with `fixedOut`. */
  maxOut?: number;
  fixedOut?: boolean;
  label: string;
  doneLabel?: string;
  suffix?: string;
}) {
  // One object URL per file. Callers key this component by file, so a new
  // pick starts from fresh state rather than being reset in an effect.
  const src = useMemo(() => URL.createObjectURL(file), [file]);
  const [natural, setNatural] = useState<Size | null>(null);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState<Offset>({ x: 0, y: 0 });
  const [busy, setBusy] = useState(false);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const pointers = useRef(new Map<number, Offset>());
  const gesture = useRef<{ start: Offset; at: Offset; pinch?: { dist: number; zoom: number } } | null>(null);
  const windowRef = useRef<HTMLDivElement | null>(null);

  const base = natural ? coverScale(view, natural) : 1;
  const scale = base * zoom;

  function onLoad(e: React.SyntheticEvent<HTMLImageElement>) {
    const size = { w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight };
    // Decoded now; the element keeps its pixels, so the URL can go. (Not in
    // an effect cleanup: StrictMode's rehearsal unmount would revoke it
    // before the image had loaded.)
    URL.revokeObjectURL(src);
    setNatural(size);
    setOffset(centred(size, coverScale(view, size), view));
  }

  function zoomTo(next: number, anchor: Offset = { x: view / 2, y: view / 2 }, from = offset, fromZoom = zoom) {
    if (!natural) return;
    const z = Math.min(MAX_ZOOM, Math.max(1, next));
    setZoom(z);
    setOffset(zoomAround(from, base * fromZoom, base * z, anchor, natural, view));
  }

  function local(e: React.PointerEvent): Offset {
    const box = windowRef.current?.getBoundingClientRect();
    return { x: e.clientX - (box?.left ?? 0), y: e.clientY - (box?.top ?? 0) };
  }

  function startGesture() {
    const pts = [...pointers.current.values()];
    if (pts.length >= 2) {
      const [a, b] = pts;
      gesture.current = {
        start: offset,
        at: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
        pinch: { dist: Math.hypot(a.x - b.x, a.y - b.y) || 1, zoom },
      };
    } else if (pts.length === 1) {
      gesture.current = { start: offset, at: pts[0] };
    } else {
      gesture.current = null;
    }
  }

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* not an active pointer (a synthetic event); the gesture still works */
    }
    pointers.current.set(e.pointerId, local(e));
    startGesture();
  }
  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!pointers.current.has(e.pointerId) || !natural || !gesture.current) return;
    pointers.current.set(e.pointerId, local(e));
    const g = gesture.current;
    const pts = [...pointers.current.values()];
    if (g.pinch && pts.length >= 2) {
      const [a, b] = pts;
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      zoomTo(g.pinch.zoom * (dist / g.pinch.dist), g.at, g.start, g.pinch.zoom);
    } else if (pts.length === 1) {
      const p = pts[0];
      setOffset(clampOffset({ x: g.start.x + p.x - g.at.x, y: g.start.y + p.y - g.at.y }, natural, scale, view));
    }
  }
  function onPointerUp(e: React.PointerEvent<HTMLDivElement>) {
    pointers.current.delete(e.pointerId);
    startGesture();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (!natural) return;
    const step = e.shiftKey ? 40 : 10;
    const moves: Record<string, Offset> = {
      ArrowLeft: { x: step, y: 0 },
      ArrowRight: { x: -step, y: 0 },
      ArrowUp: { x: 0, y: step },
      ArrowDown: { x: 0, y: -step },
    };
    if (moves[e.key]) {
      e.preventDefault();
      setOffset(clampOffset({ x: offset.x + moves[e.key].x, y: offset.y + moves[e.key].y }, natural, scale, view));
    } else if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      zoomTo(zoom + 0.1);
    } else if (e.key === "-") {
      e.preventDefault();
      zoomTo(zoom - 0.1);
    }
  }

  async function finish() {
    const img = imgRef.current;
    if (failed || !img || !natural) return;
    setBusy(true);
    try {
      const { sx, sy, side } = sourceSquare(offset, scale, view);
      const out = outputSide(side, maxOut, fixedOut);
      const canvas = document.createElement("canvas");
      canvas.width = out;
      canvas.height = out;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        onDone({ error: "This browser couldn't prepare the photo. Try another one." });
        return;
      }
      ctx.drawImage(img, sx, sy, side, side, 0, 0, out, out);
      const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", 0.88));
      if (!blob) {
        onDone({ error: "This browser couldn't prepare the photo. Try another one." });
        return;
      }
      const name = file.name.replace(/\.[^.]+$/, "") + `${suffix}.jpg`;
      onDone({ file: new File([blob], name, { type: "image/jpeg" }) });
    } finally {
      setBusy(false);
    }
  }

  const button =
    "inline-flex h-10 cursor-pointer items-center rounded-[var(--radius-pill)] px-4 text-[14px] disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

  return (
    <div
      role="group"
      aria-label={label}
      data-cropper={shape}
      className="flex w-full flex-col items-center gap-3 rounded-[16px] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)]"
    >
      {failed ? (
        <p role="alert" className="text-center text-[13px] text-[var(--text-secondary)]">
          This browser can&apos;t open that photo to position it. Save it as a JPEG or PNG and try again.
        </p>
      ) : (
        <>
          <div
            ref={windowRef}
            tabIndex={0}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onKeyDown={onKeyDown}
            aria-label="Crop area. Drag, or use the arrow keys, to reposition; pinch, or plus and minus, to zoom."
            data-testid="crop-window"
            style={{ width: view, height: view }}
            className="relative max-w-full shrink-0 cursor-grab touch-none select-none overflow-hidden rounded-[12px] bg-[var(--base-gray-200)] active:cursor-grabbing focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
          >
            {/* Not next/image: a blob: URL has no loader, and this element is
                measured and transformed directly. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              ref={imgRef}
              src={src}
              alt=""
              draggable={false}
              onLoad={onLoad}
              onError={() => {
                URL.revokeObjectURL(src);
                setFailed(true);
              }}
              style={
                natural
                  ? {
                      position: "absolute",
                      left: offset.x,
                      top: offset.y,
                      width: natural.w * scale,
                      height: natural.h * scale,
                      maxWidth: "none",
                    }
                  : { visibility: "hidden" }
              }
            />
            {shape === "circle" ? (
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 rounded-full shadow-[0_0_0_999px_rgba(0,0,0,0.45)]"
              />
            ) : (
              // Thirds, to help square the product up; the whole window is saved.
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,transparent_33.2%,rgba(255,255,255,0.45)_33.3%,transparent_33.4%,transparent_66.5%,rgba(255,255,255,0.45)_66.6%,transparent_66.7%),linear-gradient(to_bottom,transparent_33.2%,rgba(255,255,255,0.45)_33.3%,transparent_33.4%,transparent_66.5%,rgba(255,255,255,0.45)_66.6%,transparent_66.7%)]"
              />
            )}
          </div>
          <label className="flex w-full max-w-[320px] items-center gap-3 text-[12px] text-[var(--text-secondary)]">
            Zoom
            <input
              type="range"
              min={1}
              max={MAX_ZOOM}
              step={0.01}
              value={zoom}
              onChange={(e) => zoomTo(Number(e.target.value))}
              className="w-full accent-[var(--accent-primary)]"
            />
          </label>
        </>
      )}
      <div className="flex gap-2">
        {!failed ? (
          <button
            type="button"
            onClick={finish}
            disabled={busy || !natural}
            className={`${button} bg-[var(--accent-primary)] font-medium text-white`}
          >
            {busy ? "Preparing…" : doneLabel}
          </button>
        ) : null}
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className={`${button} text-[var(--text-secondary)] shadow-[var(--shadow-hairline-inset)]`}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export default ImageCropper;
