"use client";

import Link from "next/link";
import { useState } from "react";
import { ChatText, Flag, Question } from "@phosphor-icons/react";

import type { WaitingItem } from "./overview-model";

const FIRST = 5;

/**
 * Card/Waiting on you (Figma 8190:20643): the oldest five, and "See all N" in the
 * head, where N is the store's real total (questions without the store's answer,
 * reviews without its response, its open appeals). See all opens the rest of the
 * list in place; past what the dashboard sends (20 questions, 20 reviews) it points
 * to Reviews and Questions, which hold every one.
 */
export function WaitingList({ storeId, items, total }: { storeId: string; items: WaitingItem[]; total: number }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, FIRST);
  const more = total > FIRST;

  return (
    <section id="waiting" aria-labelledby="waiting-h" className="scroll-mt-4 rounded-[16px] border border-[var(--border-subtle)] p-5">
      <div className="flex items-start gap-3 pb-3">
        <div className="flex-1">
          <h2 id="waiting-h" className="text-[16px] font-semibold leading-none">Waiting on you</h2>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">Oldest first. Buyers can see how long a question has waited.</p>
        </div>
        {more ? (
          <button
            type="button"
            aria-expanded={all}
            aria-controls="waiting-list"
            onClick={() => setAll((v) => !v)}
            className="-my-1.5 py-1.5 text-[12px] text-[var(--chart-honesty-fund)] hover:underline"
          >
            {all ? "Show fewer" : `See all ${total}`}
          </button>
        ) : null}
      </div>
      {items.length === 0 ? (
        <p className="border-t border-[var(--border-subtle)] py-8 text-center text-[14px] text-[var(--text-secondary)]">
          Nothing is waiting on you. New questions and reviews show up here.
        </p>
      ) : (
        <ul id="waiting-list" className="flex flex-col" data-testid="waiting-list">
          {shown.map((w) => {
            const Icon = w.kind === "question" ? Question : w.kind === "review" ? ChatText : Flag;
            return (
              <li key={`${w.kind}-${w.id}`} className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-3">
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--surface-app)] text-[var(--text-secondary)]" aria-hidden>
                  <Icon size={16} />
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
                  <span className="truncate text-[14px]">{w.title}</span>
                  <span className={`truncate text-[12px] ${w.urgent ? "text-[var(--status-critical-fg)]" : "text-[var(--text-secondary)]"}`}>{w.note}</span>
                </span>
                <Link href={w.href} className="inline-flex h-8 shrink-0 items-center rounded-full border border-[var(--border-subtle)] px-3 text-[12px] hover:border-[var(--text-secondary)]">
                  {w.action}
                </Link>
              </li>
            );
          })}
          {all && total > items.length ? (
            <li className="border-t border-[var(--border-subtle)] pt-3 text-[12px] text-[var(--text-secondary)]">
              {total - items.length} more in{" "}
              <Link href={`/seller/${storeId}/reviews`} className="text-[var(--chart-honesty-fund)] hover:underline">Reviews</Link> and{" "}
              <Link href={`/seller/${storeId}/questions`} className="text-[var(--chart-honesty-fund)] hover:underline">Questions</Link>.
            </li>
          ) : null}
        </ul>
      )}
    </section>
  );
}
