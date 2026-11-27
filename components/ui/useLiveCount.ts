"use client";

import { useEffect, useRef, useState } from "react";

import { useAdaptivePoll } from "./useAdaptivePoll";

/**
 * A count the server rendered, kept current (MQA-032): read again from `url`
 * whenever `key` changes (pass the page's path and query, so opening a
 * conversation or a notification brings it down) and every `every` ms while
 * the tab is visible. A new server figure (router.refresh) replaces it.
 *
 * Adaptive (components/ui/useAdaptivePoll.ts): `every` while the count is
 * moving or the reader is active, backing off to 2 min while it holds still
 * and to 5 min once the reader has been idle for 10 min. Each read is a billed
 * function call on both services; an unread badge does not need 120 of them
 * an hour.
 */
export function useLiveCount(
  initial: number,
  url: string,
  pick: (body: unknown) => number | undefined,
  key: string,
  every = 30_000,
): number {
  const [state, setState] = useState({ initial, value: initial });
  if (state.initial !== initial) setState({ initial, value: initial });
  const pickRef = useRef(pick);
  useEffect(() => {
    pickRef.current = pick;
  });
  // The value on screen, so a tick can report whether it moved.
  const shown = useRef(state.value);
  useEffect(() => {
    shown.current = state.value;
  }, [state.value]);

  useAdaptivePoll(
    async () => {
      const res = await fetch(url, { cache: "no-store" }).catch(() => null);
      if (!res?.ok) return false;
      const n = pickRef.current(await res.json().catch(() => null));
      if (typeof n !== "number" || n === shown.current) return false;
      shown.current = n;
      setState((s) => (s.value === n ? s : { ...s, value: n }));
      return true;
    },
    { base: every, max: 120_000, idleAfter: 600_000, idleInterval: 300_000, immediate: true },
    `${url}|${key}`,
  );
  return state.initial !== initial ? initial : state.value;
}
