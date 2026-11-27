"use client";

/**
 * Admin/Toggle (Figma Screen/Seller/Settings 8218:24151): a 36×20 track, brand when
 * on, grey when off, the knob on the side of its state. A real `role="switch"`
 * button; name it with `labelledBy` (a visible label) or `label`.
 */
export function Switch({
  checked,
  onChange,
  label,
  labelledBy,
  describedBy,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label?: string;
  labelledBy?: string;
  describedBy?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-[var(--accent-primary)]" : "bg-[var(--border-subtle)]"
      }`}
    >
      <span
        aria-hidden
        className={`absolute top-0.5 size-4 rounded-full bg-[var(--surface-card)] shadow-[var(--shadow-segment)] transition-[left] ${checked ? "left-[18px]" : "left-0.5"}`}
      />
    </button>
  );
}
