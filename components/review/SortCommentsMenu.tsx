"use client";

import { SortMenu } from "@/components/search/SortMenu";

import { type CommentSort, type DateOrder, type RatingOrder } from "./comment-sort-model";

/**
 * "Sort comments": the search page's dropdown Menu (SortMenu, Figma Menu
 * 7761:7939), as every sort is since 2026-10-07 (owner: a dropdown, never a
 * sheet or pills). It replaced the radio sheet drawn as Figma "Sort" 1591:5408.
 *
 * Two orders, as that sheet had them: rating first, date breaking its ties
 * (comment-sort-model.ts). Each heading's choice applies at once and closes the
 * menu; the other order keeps its value.
 *
 * NO FIGMA FRAME for comment sorting itself; the sections are the thread's own
 * two orders.
 */

const RATING: { value: RatingOrder; label: string }[] = [
  { value: "most_helpful", label: "Most helpful" },
  { value: "least_helpful", label: "Least helpful" },
];

const DATE: { value: DateOrder; label: string }[] = [
  { value: "latest", label: "Latest" },
  { value: "oldest", label: "Oldest" },
];

export function SortCommentsMenu({
  anchor,
  value,
  onApply,
  onClose,
}: {
  /** The pill that opened it. */
  anchor: HTMLElement;
  value: CommentSort;
  onApply: (next: CommentSort) => void;
  onClose: () => void;
}) {
  return (
    <SortMenu<string>
      label="Sort comments"
      anchor={anchor}
      sections={[
        {
          heading: "By rating",
          options: RATING,
          value: value.rating,
          onChoose: (rating) => onApply({ ...value, rating: rating as RatingOrder }),
        },
        {
          heading: "By date",
          options: DATE,
          value: value.date,
          onChoose: (date) => onApply({ ...value, date: date as DateOrder }),
        },
      ]}
      onClose={onClose}
    />
  );
}

export default SortCommentsMenu;
