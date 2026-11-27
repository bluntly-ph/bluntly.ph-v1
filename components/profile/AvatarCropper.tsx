"use client";

import { useMemo, useRef, useState } from "react";
import { prepareImageForUpload } from "@/lib/image";

/** The on-screen crop window, in CSS pixels. */
const VIEW = 240;
/** The saved avatar, in image pixels: more than any avatar slot draws. */
const OUT = 512;
const MAX_ZOOM = 3;

type Offset = { x: number; y: number };

/**
 * Square-crop a chosen profile photo before it is uploaded (QA-019/040/042/056).
 *
 * Every avatar on the site is drawn as a circle with `object-cover`, so an
 * uncropped portrait or landscape photo lost whatever the centre crop cut off
 * — usually the top of a head — and the owner had no say in it. Here they
 * drag the photo to reposition it and zoom with the slider (or the arrow and
 * +/- keys), and what is saved is exactly the circle they saw.
 *
 * It also fixes the size failure (QA-041): the output is a 512×512 JPEG of a
 * few tens of KB, far under the Server Action body limit, whatever the phone
 * produced. A photo this browser cannot decode (HEIC outside Safari) cannot be
 * previewed or cropped; it falls back to lib/image.ts's resize-or-pass-through
 * and the server decides, as the review photo field does.
 */
export function AvatarCropper({
  file,
  onDone,
  onCancel,
}: {
  file: File;
  onDone: (result: { file: File } | { error: string }) => void;
  onCancel: () => void;
}) {
  // One object URL per file. Callers key this component by file, so a new
  // pick starts from fresh state rather than being reset in an effect.
  const src = useMemo(() => URL.createObjectURL(file), [file]);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState<Offset>({ x: 0, y: 0 });
  const [busy, setBusy] = useState(false);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const drag = useRef<{ id: number; x: number; y: number; start: Offset } | null>(null);

  const baseScale = natural ? VIEW / Math.min(natural.w, natural.h) : 1;
  const scale = baseScale * zoom;

  /** Keep the photo covering the whole window: no empty edge is ever saved. */
  function clamp(o: Offset, s = scale): Offset {
    if (!natural) return o;
    const minX = VIEW - natural.w * s;
    const minY = VIEW - natural.h * s;
    return {
      x: Math.min(0, Math.max(minX, o.x)),
      y: Math.min(0, Math.max(minY, o.y)),
    };
  }

  function onLoad(e: React.SyntheticEvent<HTMLImageElement>) {
    const w = e.currentTarget.naturalWidth;
    const h = e.currentTarget.naturalHeight;
    const s = VIEW / Math.min(w, h);
    // Decoded now; the element keeps its pixels, so the URL can go. (Not in
    // an effect cleanup: StrictMode's rehearsal unmount would revoke it
    // before the image had loaded.)
    URL.revokeObjectURL(src);
    setNatural({ w, h });
    // Start centred.
    setOffset({ x: (VIEW - w * s) / 2, y: (VIEW - h * s) / 2 });
  }

  function setZoomKeepingCentre(next: number) {
    const z = Math.min(MAX_ZOOM, Math.max(1, next));
    const s2 = baseScale * z;
    const cx = (VIEW / 2 - offset.x) / scale;
    const cy = (VIEW / 2 - offset.y) / scale;
    setZoom(z);
    setOffset(clamp({ x: VIEW / 2 - cx * s2, y: VIEW / 2 - cy * s2 }, s2));
  }

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, start: offset };
  }
  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    setOffset(clamp({ x: d.start.x + e.clientX - d.x, y: d.start.y + e.clientY - d.y }));
  }
  function onPointerUp(e: React.PointerEvent<HTMLDivElement>) {
    if (drag.current?.id === e.pointerId) drag.current = null;
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const step = e.shiftKey ? 40 : 10;
    const moves: Record<string, Offset> = {
      ArrowLeft: { x: step, y: 0 },
      ArrowRight: { x: -step, y: 0 },
      ArrowUp: { x: 0, y: step },
      ArrowDown: { x: 0, y: -step },
    };
    if (moves[e.key]) {
      e.preventDefault();
      setOffset(clamp({ x: offset.x + moves[e.key].x, y: offset.y + moves[e.key].y }));
    } else if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      setZoomKeepingCentre(zoom + 0.1);
    } else if (e.key === "-") {
      e.preventDefault();
      setZoomKeepingCentre(zoom - 0.1);
    }
  }

  async function usePhoto() {
    setBusy(true);
    try {
      const img = imgRef.current;
      if (failed || !img || !natural) {
        const prepared = await prepareImageForUpload(file, "photo");
        onDone(prepared.error ? { error: prepared.error } : { file: prepared.file });
        return;
      }
      const canvas = document.createElement("canvas");
      canvas.width = OUT;
      canvas.height = OUT;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        onDone({ error: "This browser couldn't prepare the photo. Try another one." });
        return;
      }
      const side = VIEW / scale;
      ctx.drawImage(img, -offset.x / scale, -offset.y / scale, side, side, 0, 0, OUT, OUT);
      const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", 0.88));
      if (!blob) {
        onDone({ error: "This browser couldn't prepare the photo. Try another one." });
        return;
      }
      const name = file.name.replace(/\.[^.]+$/, "") + "-avatar.jpg";
      onDone({ file: new File([blob], name, { type: "image/jpeg" }) });
    } finally {
      setBusy(false);
    }
  }

  const button =
    "inline-flex h-9 cursor-pointer items-center rounded-[var(--radius-pill)] px-4 text-[13px] disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

  return (
    <div
      role="group"
      aria-label="Position your profile photo"
      className="mt-4 flex w-full max-w-[320px] flex-col items-center gap-3 rounded-[16px] p-4 shadow-[var(--shadow-hairline-inset)]"
    >
      {failed ? (
        <p className="text-center text-[13px] text-[var(--text-secondary)]">
          This browser can&apos;t preview that photo, so it can&apos;t be positioned here.
          It will be uploaded as it is.
        </p>
      ) : (
        <>
          <div
            tabIndex={0}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onKeyDown={onKeyDown}
            aria-label="Photo crop area. Drag, or use the arrow keys, to reposition; plus and minus to zoom."
            style={{ width: VIEW, height: VIEW }}
            className="relative shrink-0 cursor-grab touch-none select-none overflow-hidden rounded-[12px] bg-[var(--base-gray-200)] active:cursor-grabbing focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
          >
            {src ? (
              // Not next/image: a blob: URL has no loader, and this element
              // is measured and transformed directly.
              // eslint-disable-next-line @next/next/no-img-element
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
            ) : null}
            {/* The circle that will be saved; outside it is dimmed. */}
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 rounded-full shadow-[0_0_0_999px_rgba(0,0,0,0.45)]"
            />
          </div>
          <label className="flex w-full items-center gap-3 text-[12px] text-[var(--text-secondary)]">
            Zoom
            <input
              type="range"
              min={1}
              max={MAX_ZOOM}
              step={0.01}
              value={zoom}
              onChange={(e) => setZoomKeepingCentre(Number(e.target.value))}
              className="w-full accent-[var(--accent-primary)]"
            />
          </label>
        </>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={usePhoto}
          disabled={busy || (!failed && !natural)}
          className={`${button} bg-[var(--accent-primary)] font-medium text-white`}
        >
          {busy ? "Preparing…" : "Use photo"}
        </button>
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
