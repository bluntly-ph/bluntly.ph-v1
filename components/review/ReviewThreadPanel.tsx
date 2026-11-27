"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowsClockwise, ClockCounterClockwise, ImageSquare, Trash } from "@phosphor-icons/react";

import { DeleteReviewDialog } from "@/components/review/DeleteReviewDialog";
import { ReviewPhotosField } from "@/components/reviews/ReviewPhotosField";
import { cleanPhotos } from "@/components/reviews/review-media-model";

type Entry = {
  id: string;
  title: string;
  star_rating: number;
  published_at: string | null;
  created_at: string;
  is_root: boolean;
  is_latest: boolean;
};

/** Business Rules §4: one photo swap, within 72 hours of publishing. */
const PHOTO_SWAP_MS = 72 * 60 * 60 * 1000;

const CONTROL =
  "inline-flex cursor-pointer items-center gap-1.5 rounded-[var(--radius-pill)] px-3 py-1.5 text-[12px] shadow-[var(--shadow-hairline-inset)] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

function day(iso: string): string {
  return new Date(iso).toLocaleDateString("en-PH", { year: "numeric", month: "short", day: "numeric" });
}

async function problem(res: Response, fallback: string): Promise<string> {
  const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
  return typeof p.detail === "string" ? p.detail : fallback;
}

/**
 * A review's thread (Business Rules §4), under the review.
 *
 * Published words are frozen: a reviewer's changed mind is a NEW dated entry on
 * the same thread, at most once every three calendar months, and only the
 * latest entry counts toward the product's rating. Readers see every entry,
 * dated, with the one that counts marked; on an earlier entry they are pointed
 * to the latest.
 *
 * The author also gets the three things the rules allow them: add an update
 * (when the cooldown has passed), replace the photos once within 72 hours of
 * publishing (the whole ordered set, PATCH {photo_urls} — a review can carry
 * several, so swapping in a single photo would silently drop the rest), and delete — an update on its own, or the original, which takes
 * the whole thread. Delete opens the one shared dialog (DeleteReviewDialog),
 * which asks for the word "delete" typed out first.
 */
export function ReviewThreadPanel({
  reviewId,
  entries,
  nextUpdateAt,
  isOwn,
  isRoot,
  publishedAt,
  photoReplacedAt,
  photos = [],
}: {
  reviewId: string;
  entries: Entry[];
  nextUpdateAt: string | null;
  isOwn: boolean;
  isRoot: boolean;
  publishedAt: string | null;
  photoReplacedAt: string | null;
  /** The review's own photos now, in order (reviewPhotos); the swap starts from them. */
  photos?: string[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  // The one-time swap edits the whole set: the current photos are kept,
  // removed or replaced, new ones are cropped first (QA-062), and nothing is
  // saved until "Save photos" — the swap is spent only then.
  const [swapping, setSwapping] = useState(false);
  const [nextPhotos, setNextPhotos] = useState<string[]>(photos);
  const [uploading, setUploading] = useState(false);
  // Read once, at first render: this decides which controls are offered, and
  // the server enforces the same windows whatever the clock here says.
  const [now] = useState(() => Date.now());

  const latest = entries.find((e) => e.is_latest) ?? null;
  const onLatest = latest?.id === reviewId;
  const updateOpen = nextUpdateAt !== null && now >= new Date(nextUpdateAt).getTime();
  const photoSwapOpen =
    photoReplacedAt === null &&
    publishedAt !== null &&
    now - new Date(publishedAt).getTime() <= PHOTO_SWAP_MS;

  const unchanged =
    nextPhotos.length === photos.length && nextPhotos.every((u, i) => u === photos[i]);

  async function savePhotos() {
    const photo_urls = cleanPhotos(nextPhotos);
    // A swap replaces photos; it does not remove them (422 photo_required).
    if (!photo_urls.length || unchanged) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`/api/bff/api/v1/reviews/${reviewId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ photo_urls }),
      });
      if (!res.ok) {
        setError(await problem(res, "Couldn't replace the photos."));
        return;
      }
      setSwapping(false);
      setNotice("Photos replaced. That was your one swap for this review.");
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const multiple = entries.length > 1;
  if (!multiple && !isOwn) return null;

  return (
    <section aria-labelledby="thread-heading" className="mt-8 rounded-[16px] p-4 shadow-[var(--shadow-hairline-inset)]">
      <h2 id="thread-heading" className="flex items-center gap-2 text-[14px] font-semibold text-[var(--text-primary)]">
        <ClockCounterClockwise size={18} aria-hidden="true" />
        {multiple ? `This review has ${entries.length} entries` : "Your review"}
      </h2>

      {multiple && !onLatest && latest ? (
        <p className="mt-2 text-[12px] text-[var(--text-secondary)]">
          You&apos;re reading an earlier entry.{" "}
          <Link href={`/reviews/${latest.id}`} className="font-medium text-[var(--accent-primary)] hover:underline">
            Read the latest update
          </Link>
        </p>
      ) : null}

      {multiple ? (
        <ol className="mt-3 flex flex-col gap-2">
          {entries.map((e) => (
            <li key={e.id} className="flex flex-wrap items-baseline gap-x-2 text-[12px]">
              <time dateTime={e.published_at ?? e.created_at} className="text-[var(--text-secondary)]">
                {day(e.published_at ?? e.created_at)}
              </time>
              {e.id === reviewId ? (
                <span className="font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">{e.title}</span>
              ) : (
                <Link href={`/reviews/${e.id}`} className="text-[var(--text-primary)] underline-offset-4 hover:underline [overflow-wrap:anywhere]">
                  {e.title}
                </Link>
              )}
              <span className="text-[var(--text-secondary)]">{e.star_rating.toFixed(1)}★</span>
              {e.is_root ? <span className="text-[var(--text-muted)]">Original</span> : <span className="text-[var(--text-muted)]">Update</span>}
              {e.is_latest ? (
                <span className="rounded-[var(--radius-pill)] bg-[color-mix(in_srgb,var(--accent-success)_14%,transparent)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-primary)]">
                  Counts toward the rating
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}

      {isOwn ? (
        <>
          <p className="mt-3 text-[12px] leading-[18px] text-[var(--text-secondary)]">
            Published reviews can&apos;t be edited. If your view changes, add a dated update — once every three
            months. The latest entry is the one that counts.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {updateOpen ? (
              <Link
                href={`/reviews/new?update=${reviewId}`}
                className={`${CONTROL} text-[var(--accent-primary)] no-underline`}
              >
                <ArrowsClockwise size={16} aria-hidden="true" /> Add an update
              </Link>
            ) : nextUpdateAt ? (
              <span className={`${CONTROL} cursor-default text-[var(--text-muted)]`}>
                <ArrowsClockwise size={16} aria-hidden="true" /> Next update from {day(nextUpdateAt)}
              </span>
            ) : null}

            {photoSwapOpen && !swapping && !notice ? (
              <button
                type="button"
                onClick={() => {
                  setNextPhotos(photos);
                  setSwapping(true);
                  setError(null);
                }}
                disabled={busy}
                className={`${CONTROL} text-[var(--text-primary)]`}
              >
                <ImageSquare size={16} aria-hidden="true" /> {photos.length ? "Replace photos (once)" : "Add photos (once)"}
              </button>
            ) : null}

            <button
              type="button"
              onClick={() => {
                setDeleting(true);
                setError(null);
              }}
              disabled={busy}
              className={`${CONTROL} text-[var(--text-secondary)] hover:text-[var(--accent-danger)]`}
            >
              <Trash size={16} aria-hidden="true" /> {isRoot ? "Delete review" : "Delete this update"}
            </button>
          </div>

          {swapping ? (
            <div className="mt-4">
              <p className="mb-3 text-[12px] leading-[18px] text-[var(--text-secondary)]">
                Keep, remove or replace your photos, then save. You can do this once, and a review keeps at least
                one photo after a swap.
              </p>
              <ReviewPhotosField urls={nextPhotos} onChange={setNextPhotos} onBusyChange={setUploading} />
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void savePhotos()}
                  disabled={busy || uploading || unchanged || nextPhotos.length === 0}
                  className={`${CONTROL} text-[var(--accent-primary)]`}
                >
                  {busy ? "Saving…" : "Save photos (uses your one swap)"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSwapping(false);
                    setNextPhotos(photos);
                  }}
                  disabled={busy}
                  className={`${CONTROL} text-[var(--text-secondary)]`}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          <DeleteReviewDialog
            reviewId={reviewId}
            isRoot={isRoot}
            open={deleting}
            onClose={() => setDeleting(false)}
          />
        </>
      ) : null}

      {error ? (
        <p role="alert" className="mt-2 text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="mt-2 text-[12px] text-[var(--text-secondary)]">
          {notice}
        </p>
      ) : null}
    </section>
  );
}
