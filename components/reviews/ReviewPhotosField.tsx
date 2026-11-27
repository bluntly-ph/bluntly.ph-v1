"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { ArrowClockwise, Image as ImageIcon, Plus, WarningCircle, X } from "@phosphor-icons/react/dist/ssr";

import { COMPOSER_FOCUS_RING } from "@/components/reviews/composer-styles";
import { MAX_REVIEW_PHOTOS, addPhoto, removePhoto, replacePhoto } from "@/components/reviews/review-media-model";
import { ImageCropper } from "@/components/ui/ImageCropper";
import { prepareImageForUpload } from "@/lib/image";

/**
 * The reviewer's own photos: pick several, position each, remove, replace,
 * clear (owner requirement, 2026-10-05).
 *
 * Built on the single-upload step it replaces — Figma "Reviewer Page - Step 6"
 * (4443:555) and 6.1 — and the seller review's photo tiles, the multi-photo
 * treatment the design system already has:
 *  - empty: the frame's 390px card, Image glyph, "Tap to upload your product
 *    photos" / "Use your own photos of the product";
 *  - with photos: the first fills that card edge to edge (6.1), the rest are
 *    square tiles at radius 16 in a three-up row under it (the most a review
 *    takes is four, so one row always fits), with an "Add more" tile while
 *    there is room. Order is the order picked; there is no reordering because no frame
 *    draws one.
 *
 * Each picked file is cropped to the square first (QA-062) and only the crop is
 * uploaded, one POST /reviews/photo per photo. A photo that is still uploading
 * or failed has its own tile — with "Retry" and "Remove" — and never reaches
 * `urls` (the draft) until the API has stored it.
 *
 * NO PHOTO = NO DEFAULT PHOTO: with nothing uploaded, nothing is drawn but the
 * empty card. The product's image is never shown or sent as review media.
 */

type Pending = {
  id: number;
  /** As picked, so the reviewer can re-position it. */
  source: File;
  /** The crop that is (being) uploaded. */
  crop: File | null;
  status: "cropping" | "uploading" | "error";
  error?: string;
  /** Replacing the photo at this index rather than adding one. */
  replaces?: number;
};

let nextId = 1;

export function ReviewPhotosField({
  urls,
  onChange,
  max = MAX_REVIEW_PHOTOS,
  onBusyChange,
  emptyTitle,
  emptyHint,
}: {
  urls: string[];
  onChange: (urls: string[]) => void;
  max?: number;
  /** True while anything is cropping or uploading, so the step can wait. */
  onBusyChange?: (busy: boolean) => void;
  emptyTitle?: string;
  emptyHint?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<Pending[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  // What the next pick is for: adding photos, or replacing the one at an index.
  const pickFor = useRef<number | null>(null);
  const controllers = useRef(new Map<number, AbortController>());
  // The latest list, for uploads that finish after a later change.
  const latest = useRef(urls);
  useEffect(() => {
    latest.current = urls;
  }, [urls]);

  const busy = pending.some((p) => p.status !== "error");
  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);

  // Leaving the step abandons uploads still in flight (QA-063).
  useEffect(() => {
    const live = controllers.current;
    return () => {
      for (const c of live.values()) c.abort();
      live.clear();
    };
  }, []);

  const adding = pending.filter((p) => p.replaces === undefined).length;
  const room = Math.max(0, max - urls.length - adding);
  const cropping = pending.find((p) => p.status === "cropping");
  const multi = max > 1;

  function open(replaces: number | null) {
    pickFor.current = replaces;
    if (input.current) {
      input.current.multiple = replaces === null && multi;
      input.current.click();
    }
  }

  function picked(files: File[]) {
    setNotice(null);
    const images = files.filter((f) => f.type === "" || f.type.startsWith("image/"));
    const refused = files.length - images.length;
    const replaces = pickFor.current;
    let take = images;
    if (replaces === null) {
      take = images.slice(0, room);
    } else {
      take = images.slice(0, 1);
    }
    const dropped = images.length - take.length;
    const parts: string[] = [];
    if (refused) parts.push(refused === 1 ? "One file isn't an image." : `${refused} files aren't images.`);
    if (dropped) parts.push(`A review can carry up to ${max} photos, so ${dropped === 1 ? "one was" : `${dropped} were`} left out.`);
    if (parts.length) setNotice(parts.join(" "));
    if (take.length) {
      setPending((list) => [
        ...list,
        ...take.map((source) => ({
          id: nextId++,
          source,
          crop: null,
          status: "cropping" as const,
          replaces: replaces ?? undefined,
        })),
      ]);
    }
    if (input.current) input.current.value = "";
  }

  function patchPending(id: number, next: Partial<Pending> | null) {
    setPending((list) =>
      next === null ? list.filter((p) => p.id !== id) : list.map((p) => (p.id === id ? { ...p, ...next } : p)),
    );
  }

  async function send(item: Pending, crop: File) {
    controllers.current.get(item.id)?.abort();
    const controller = new AbortController();
    controllers.current.set(item.id, controller);
    patchPending(item.id, { crop, status: "uploading", error: undefined });
    try {
      const prepared = await prepareImageForUpload(crop, "photo");
      if (controller.signal.aborted) return;
      if (prepared.error) {
        patchPending(item.id, { status: "error", error: prepared.error });
        return;
      }
      const body = new FormData();
      body.append("file", prepared.file);
      const res = await fetch("/api/bff/api/v1/reviews/photo", { method: "POST", body, signal: controller.signal });
      if (controller.signal.aborted) return;
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string };
        patchPending(item.id, { status: "error", error: p.detail ?? "That photo couldn't be uploaded." });
        return;
      }
      const { url } = (await res.json()) as { url: string };
      if (controller.signal.aborted) return;
      const now = latest.current;
      const next = item.replaces !== undefined && item.replaces < now.length
        ? replacePhoto(now, item.replaces, url)
        : addPhoto(now, url, max);
      latest.current = next;
      onChange(next);
      patchPending(item.id, null);
    } catch {
      if (!controller.signal.aborted) patchPending(item.id, { status: "error", error: "Couldn't reach the server." });
    } finally {
      if (controllers.current.get(item.id) === controller) controllers.current.delete(item.id);
    }
  }

  function drop(id: number) {
    controllers.current.get(id)?.abort();
    controllers.current.delete(id);
    patchPending(id, null);
  }

  function remove(index: number) {
    setNotice(null);
    const next = removePhoto(urls, index);
    latest.current = next;
    onChange(next);
  }

  function clearAll() {
    for (const c of controllers.current.values()) c.abort();
    controllers.current.clear();
    setPending([]);
    setNotice(null);
    latest.current = [];
    onChange([]);
  }

  const [first, ...rest] = urls;
  const tilePending = pending.filter((p) => p.status !== "cropping");

  return (
    <div>
      {cropping ? (
        <div className="mb-6">
          <ImageCropper
            key={cropping.id}
            file={cropping.source}
            view={Math.min(320, typeof window === "undefined" ? 320 : window.innerWidth - 64)}
            maxOut={1600}
            label={
              pending.filter((p) => p.status === "cropping").length > 1
                ? `Position your photo (${pending.filter((p) => p.status === "cropping").length} to go)`
                : "Position your photo"
            }
            doneLabel="Use this crop"
            onCancel={() => drop(cropping.id)}
            onDone={(result) => {
              if ("error" in result) {
                patchPending(cropping.id, { status: "error", error: result.error });
                return;
              }
              void send(cropping, result.file);
            }}
          />
          <p className="mt-3 text-center text-[12px] text-[var(--text-secondary)]">
            Only the square you see is uploaded.
          </p>
        </div>
      ) : null}

      {first ? (
        <div className="relative h-[390px] w-full max-w-full overflow-hidden rounded-[16px] bg-[var(--surface-card)] shadow-[var(--shadow-card)]">
          <Image src={first} alt="Your photo 1" fill sizes="(min-width: 768px) 390px, 100vw" className="object-cover" />
          <PhotoControls
            index={0}
            total={urls.length}
            onReplace={() => open(0)}
            onRemove={() => remove(0)}
            disabled={Boolean(cropping)}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => open(null)}
          disabled={room === 0 || Boolean(cropping)}
          aria-label={multi ? "Upload your product photos" : "Upload your product photo"}
          className={`relative block h-[390px] w-full cursor-pointer overflow-hidden rounded-[16px] bg-[var(--surface-card)] shadow-[var(--shadow-card)] disabled:cursor-default ${COMPOSER_FOCUS_RING}`}
        >
          <span className="flex h-full flex-col items-center px-4 pt-[90px] text-center">
            <ImageIcon size={64} weight="fill" aria-hidden="true" className="text-[var(--base-black)]" />
            <span className="mt-2 text-[14px] leading-none text-[var(--text-primary)]">
              {busy && tilePending.length ? "Uploading…" : emptyTitle ?? (multi ? "Tap to upload your product photos" : "Tap to upload your product photo")}
            </span>
            <span className="mt-[11px] text-[12px] leading-[18px] text-[rgba(32,32,32,0.3)] [text-wrap:balance]">
              {emptyHint ?? (multi ? `Use your own photos of the product, up to ${max}` : "Use your own photo of the product")}
            </span>
          </span>
        </button>
      )}

      {rest.length || tilePending.length || (first && room > 0) ? (
        <ul className="mt-3 grid grid-cols-3 gap-3" aria-label="Your photos">
          {rest.map((url, i) => (
            <li
              key={url}
              className="relative aspect-square min-w-0 overflow-hidden rounded-[16px] shadow-[var(--shadow-card)]"
            >
              <Image src={url} alt={`Your photo ${i + 2}`} fill sizes="(min-width: 768px) 122px, 30vw" className="object-cover" />
              <PhotoControls
                index={i + 1}
                total={urls.length}
                onReplace={() => open(i + 1)}
                onRemove={() => remove(i + 1)}
                disabled={Boolean(cropping)}
                compact
              />
            </li>
          ))}

          {tilePending.map((p) => (
            <li
              key={p.id}
              className="relative flex aspect-square min-w-0 flex-col items-center justify-center gap-1.5 overflow-hidden rounded-[16px] bg-[var(--surface-card)] p-2 text-center shadow-[var(--shadow-card)]"
            >
              {p.status === "uploading" ? (
                <>
                  <span aria-hidden="true" className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--base-gray-200)] border-t-[var(--accent-primary)]" />
                  <span className="text-[10px] leading-none text-[var(--base-gray-500)]">Uploading…</span>
                  <span className="w-full min-w-0 truncate text-[10px] leading-none text-[var(--base-gray-400)]" title={p.source.name}>
                    {p.source.name}
                  </span>
                </>
              ) : (
                <>
                  <WarningCircle size={20} weight="fill" aria-hidden="true" className="text-[var(--accent-danger)]" />
                  <span role="alert" className="line-clamp-3 w-full min-w-0 break-words text-[10px] leading-[13px] text-[var(--accent-danger)] [overflow-wrap:anywhere]">
                    {p.error}
                  </span>
                  <span className="flex gap-2">
                    {p.crop ? (
                      <button
                        type="button"
                        onClick={() => void send(p, p.crop as File)}
                        className={`inline-flex cursor-pointer items-center gap-0.5 rounded-full text-[10px] font-medium leading-none text-[var(--accent-primary)] underline-offset-2 hover:underline ${COMPOSER_FOCUS_RING}`}
                      >
                        <ArrowClockwise size={12} aria-hidden="true" />
                        Retry
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => drop(p.id)}
                      className={`cursor-pointer rounded-full text-[10px] leading-none text-[var(--text-primary)] underline-offset-2 hover:underline ${COMPOSER_FOCUS_RING}`}
                    >
                      Remove
                    </button>
                  </span>
                </>
              )}
            </li>
          ))}

          {first && room > 0 ? (
            <li className="min-w-0">
              <button
                type="button"
                onClick={() => open(null)}
                disabled={Boolean(cropping)}
                aria-label="Add more photos"
                className={`flex aspect-square w-full cursor-pointer flex-col items-center justify-center rounded-[16px] bg-[var(--surface-card)] text-[10px] leading-none text-[var(--base-gray-400)] shadow-[var(--shadow-card)] disabled:cursor-default ${COMPOSER_FOCUS_RING}`}
              >
                <Plus size={32} aria-hidden="true" className="text-[var(--base-black)]" />
                <span className="mt-[9px]">Add more</span>
              </button>
            </li>
          ) : null}
        </ul>
      ) : null}

      {multi && urls.length > 0 ? (
        <p className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[12px] leading-none text-[var(--text-secondary)]">
          <span aria-live="polite">
            {urls.length} of {max} photos
          </span>
          <button
            type="button"
            onClick={clearAll}
            className={`cursor-pointer rounded-full text-[12px] leading-none text-[var(--text-primary)] underline-offset-4 hover:underline ${COMPOSER_FOCUS_RING}`}
          >
            Clear all
          </button>
        </p>
      ) : null}

      {notice ? (
        <p role="alert" className="mt-3 text-center text-[13px] text-[var(--accent-danger)]">
          {notice}
        </p>
      ) : null}

      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        multiple={multi}
        data-testid="review-photos-input"
        className="hidden"
        onChange={(e) => picked(Array.from(e.target.files ?? []))}
      />
    </div>
  );
}

/** Replace and remove, over a placed photo. */
function PhotoControls({
  index,
  total,
  onReplace,
  onRemove,
  disabled,
  compact = false,
}: {
  index: number;
  total: number;
  onReplace: () => void;
  onRemove: () => void;
  disabled: boolean;
  compact?: boolean;
}) {
  const n = `photo ${index + 1}${total > 1 ? ` of ${total}` : ""}`;
  return (
    <>
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        aria-label={`Remove ${n}`}
        className={`absolute right-1.5 top-1.5 grid h-7 w-7 cursor-pointer place-items-center rounded-full bg-[rgba(32,32,32,0.7)] text-white disabled:opacity-50 ${COMPOSER_FOCUS_RING}`}
      >
        <X size={14} weight="bold" aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={onReplace}
        disabled={disabled}
        aria-label={`Replace ${n}`}
        className={`absolute bottom-1.5 left-1.5 cursor-pointer rounded-full bg-[rgba(32,32,32,0.7)] px-2.5 text-white disabled:opacity-50 ${
          compact ? "h-6 text-[10px]" : "h-8 text-[12px]"
        } leading-none ${COMPOSER_FOCUS_RING}`}
      >
        Replace
      </button>
    </>
  );
}

export default ReviewPhotosField;
