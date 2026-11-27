"use client";

import Image from "next/image";
import { useRef, useState } from "react";

/**
 * A published review's photos, when it has more than one.
 *
 * Figma "Screen/Product" (7651:5805) → "Gallery" (7651:5840), read 2026-10-05:
 * the photo square at radius 12 on #e1e1e1; the count "1/3" in 12px Regular
 * #f2f2f2 on a #8c8c8c pill (13 x 7 padding, radius 20) 12px from the top
 * right; the pager a 20px #8c8c8c pill centred 24px above the bottom edge
 * holding 8px #f2f2f2 dots on a 12px pitch. The frame draws every dot alike;
 * here the dots other than the current one are dimmed so the pager reads.
 * Drawn only for a review with more than one photo (owner, 2026-10-05).
 * Native horizontal scroll-snap, so it swipes on touch and scrolls by trackpad
 * or keyboard; the dots are buttons that go to their photo.
 *
 * Only the reviewer's own uploads come here (reviewPhotos). Never the
 * product's image.
 */
export function ReviewPhotoCarousel({ photos, alt }: { photos: string[]; alt: string }) {
  const track = useRef<HTMLDivElement>(null);
  const [at, setAt] = useState(0);

  function go(i: number) {
    const el = track.current;
    if (!el) return;
    el.scrollTo({ left: i * el.clientWidth, behavior: "smooth" });
  }

  return (
    <div className="relative overflow-hidden rounded-[12px] bg-[#e1e1e1]">
      <div
        ref={track}
        tabIndex={0}
        role="region"
        aria-roledescription="carousel"
        aria-label={`Reviewer's photos, ${photos.length}`}
        onScroll={(e) => {
          const el = e.currentTarget;
          const i = Math.round(el.scrollLeft / Math.max(1, el.clientWidth));
          if (i !== at) setAt(Math.min(photos.length - 1, Math.max(0, i)));
        }}
        className="flex aspect-square w-full snap-x snap-mandatory overflow-x-auto overscroll-x-contain [scrollbar-width:none] focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--accent-primary)] [&::-webkit-scrollbar]:hidden"
      >
        {photos.map((src, i) => (
          <div
            key={src}
            role="group"
            aria-roledescription="slide"
            aria-label={`${i + 1} of ${photos.length}`}
            className="relative h-full w-full shrink-0 snap-center"
          >
            <Image
              src={src}
              alt={i === 0 ? alt : `${alt} — photo ${i + 1}`}
              fill
              sizes="(min-width: 480px) 28rem, 100vw"
              priority={i === 0}
              className="object-cover"
            />
          </div>
        ))}
      </div>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-3 rounded-[20px] bg-[var(--base-gray-400)] px-[13px] py-[7px] text-[12px] leading-4 text-[#f2f2f2]"
      >
        {at + 1}/{photos.length}
      </span>
      <div className="absolute bottom-6 left-1/2 flex h-5 -translate-x-1/2 items-center gap-1 rounded-[20px] bg-[var(--base-gray-400)] px-1.5">
        {photos.map((src, i) => (
          <button
            key={src}
            type="button"
            onClick={() => go(i)}
            aria-label={`Show photo ${i + 1} of ${photos.length}`}
            aria-current={i === at ? "true" : undefined}
            className={`h-2 w-2 cursor-pointer rounded-full bg-[#f2f2f2] transition-opacity focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-white ${
              i === at ? "" : "opacity-50"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

export default ReviewPhotoCarousel;
