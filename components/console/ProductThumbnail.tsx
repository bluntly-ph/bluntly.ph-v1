import Image from "next/image";
import { Package } from "@phosphor-icons/react/dist/ssr";

import { usablePhoto } from "@/lib/image";

/**
 * Figma component "Product Thumbnail" (console tables: Products, Queue / All
 * reviews): the product's listing image in a rounded square, or the package
 * mark on grey when there is none. Product context only: a review's own photo
 * is never drawn here, and a product image is never presented as a review's.
 */
export function ProductThumbnail({ url, size = 32 }: { url: string | null | undefined; size?: 30 | 32 | 40 }) {
  const src = usablePhoto(url ?? null);
  const box = size === 40 ? "size-10" : size === 30 ? "size-[30px]" : "size-8";
  return src ? (
    <Image src={src} alt="" width={size} height={size} unoptimized className={`${box} shrink-0 rounded-[8px] object-cover`} />
  ) : (
    <span aria-hidden className={`${box} grid shrink-0 place-items-center rounded-[8px] border border-[var(--border-subtle)] bg-[var(--surface-app)] text-[var(--text-secondary)]`}>
      <Package size={16} />
    </span>
  );
}
