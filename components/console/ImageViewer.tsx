"use client";

import { useState } from "react";

import { AdminModal } from "@/components/admin/AdminModal";

/**
 * Overlay/Admin/ImageViewer (Figma 8237:25416): one image at a readable size,
 * its file name and what it is ("Image · PNG · 420 KB · sent 1 day ago"), with
 * Download and Close. Used for message attachments and review photos instead of
 * a bare new tab.
 *
 * `src` is null while a private file's short-lived link is being fetched;
 * `error` says why it couldn't be shown. Download is either a plain link or,
 * for private files, a callback that fetches a download link first.
 */
export function ImageViewer({
  title,
  src,
  alt,
  meta,
  error,
  downloadHref,
  onDownload,
  onClose,
}: {
  title: string;
  src: string | null;
  alt: string;
  meta: string;
  error?: string | null;
  downloadHref?: string | null;
  onDownload?: () => Promise<string | null>;
  onClose: () => void;
}) {
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const BUTTON = "grid h-9 place-items-center rounded-full border border-[var(--text-primary)] px-4 text-[12px] hover:bg-[var(--surface-app)]";
  return (
    <AdminModal title={title} width={720} onClose={onClose}>
      <div className="flex flex-col gap-3 px-6 pb-5 pt-4">
        <div className="grid min-h-[240px] place-items-center overflow-hidden rounded-[12px] bg-[var(--surface-app)]">
          {error ? (
            <p role="alert" className="p-6 text-center text-[14px] text-[var(--text-secondary)]">
              {error}
            </p>
          ) : src ? (
            // A signed or remote URL of any size: a plain img, scaled to fit.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={src} alt={alt} className="max-h-[60vh] w-auto max-w-full object-contain" data-testid="image-viewer-img" />
          ) : (
            <p role="status" className="p-6 text-[14px] text-[var(--text-secondary)]">
              Loading the image…
            </p>
          )}
        </div>
        <p className="text-[12px] text-[var(--text-secondary)]" suppressHydrationWarning>
          {meta}
        </p>
        {downloadError ? (
          <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
            {downloadError}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        {downloadHref ? (
          <a href={downloadHref} download target="_blank" rel="noopener noreferrer" className={BUTTON}>
            Download
          </a>
        ) : onDownload ? (
          <button
            type="button"
            className={BUTTON}
            onClick={() => {
              setDownloadError(null);
              void onDownload().then((url) => {
                if (url) window.location.assign(url);
                else setDownloadError("The file couldn’t be downloaded. Try again.");
              });
            }}
          >
            Download
          </button>
        ) : null}
        <button type="button" onClick={onClose} className="h-9 rounded-full bg-[var(--accent-primary)] px-5 text-[12px] text-white">
          Close
        </button>
      </div>
    </AdminModal>
  );
}
