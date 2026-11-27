/** /unsubscribe (backend 0085): what each signed link turns off, in words. */

export type UnsubscribeScope = "email" | "weekly_summary";

export const SCOPE_COPY: Record<UnsubscribeScope, { what: string; done: string }> = {
  email: {
    what: "store notifications by email",
    done: "You won't get store notifications by email any more. They still show up in the app.",
  },
  weekly_summary: {
    what: "the Monday weekly summary",
    done: "You won't get the weekly summary any more.",
  },
};

export function scopeOf(value: unknown): UnsubscribeScope | null {
  return value === "email" || value === "weekly_summary" ? value : null;
}
