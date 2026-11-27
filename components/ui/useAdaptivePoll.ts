"use client";

import { useEffect, useRef } from "react";

/**
 * A poll that costs little when nothing is happening.
 *
 * Every tick of a live poll is a request to /api/bff, which is a billed
 * function invocation on the frontend AND on the backend. A fixed 4-second
 * poll on an open thread was ~900 of each per hour per visible tab, almost all
 * of them answering "nothing new". This keeps the same "a reply appears
 * without a reload" behaviour while the reader is active, and slows down when
 * they are not:
 *
 * - Runs only while the tab is visible. Becoming visible again ticks at once
 *   (the catch-up the old pollers did on `visibilitychange`).
 * - Starts at `base`. Each tick that reports no change doubles the delay, up
 *   to `max`. A change, or any reader input (pointer, key, wheel, touch,
 *   window focus), drops it back to `base`.
 * - After `idleAfter` with no input, the delay becomes `idleInterval`: a tab
 *   left open on a second monitor still updates, just rarely. The first input
 *   after that ticks immediately, so the reader sees current data the moment
 *   they come back.
 *
 * `tick` returns true when it found something new, false when it did not.
 * A failed tick (throws) counts as "no change" so an outage backs off instead
 * of hammering the API.
 */
export type AdaptivePollOptions = {
  /** Delay between ticks while the reader is active and data is changing. */
  base: number;
  /** Ceiling for the back-off while nothing changes. Defaults to `base`. */
  max?: number;
  /** No input for this long counts as idle. Defaults to never. */
  idleAfter?: number;
  /** Delay between ticks while idle. Defaults to `max`. */
  idleInterval?: number;
  /** Tick once as soon as the poll starts (before the first delay). */
  immediate?: boolean;
  /** False pauses the poll entirely. */
  enabled?: boolean;
};

const INPUT_EVENTS = ["pointerdown", "keydown", "wheel", "touchstart", "focus"] as const;

export function useAdaptivePoll(
  tick: () => Promise<boolean>,
  options: AdaptivePollOptions,
  /** Restart the poll from `base` whenever this value changes (a new path, a new signature). */
  resetKey?: unknown,
): void {
  const { base, enabled = true, immediate = false } = options;
  const max = Math.max(options.max ?? base, base);
  const idleAfter = options.idleAfter ?? Number.POSITIVE_INFINITY;
  const idleInterval = Math.max(options.idleInterval ?? max, base);

  const tickRef = useRef(tick);
  useEffect(() => {
    tickRef.current = tick;
  });

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let running = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = base;
    let lastInput = Date.now();

    const visible = () => document.visibilityState === "visible";
    const idle = () => Date.now() - lastInput >= idleAfter;

    const clear = () => {
      if (timer !== undefined) clearTimeout(timer);
      timer = undefined;
    };

    const schedule = () => {
      clear();
      if (stopped || !visible()) return; // parked; visibilitychange wakes it
      timer = setTimeout(() => void run(), idle() ? idleInterval : delay);
    };

    const run = async () => {
      timer = undefined;
      if (stopped || running) return;
      if (!visible()) return;
      running = true;
      let changed = false;
      try {
        changed = await tickRef.current();
      } catch {
        changed = false;
      }
      running = false;
      if (stopped) return;
      delay = changed ? base : Math.min(delay * 2, max);
      schedule();
    };

    const onInput = () => {
      const wasIdle = idle();
      lastInput = Date.now();
      if (wasIdle) {
        // Back from idle: show current data now rather than after a delay.
        delay = base;
        clear();
        void run();
      } else if (delay !== base) {
        delay = base;
        if (!running) schedule();
      }
    };

    const onVisibility = () => {
      if (visible()) {
        lastInput = Date.now();
        delay = base;
        clear();
        void run();
      } else {
        clear();
      }
    };

    for (const type of INPUT_EVENTS) window.addEventListener(type, onInput, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);

    if (immediate) void run();
    else schedule();

    return () => {
      stopped = true;
      clear();
      for (const type of INPUT_EVENTS) window.removeEventListener(type, onInput);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [enabled, base, max, idleAfter, idleInterval, immediate, resetKey]);
}
