import { CheckCircle, Warning } from "@phosphor-icons/react/dist/ssr";

/**
 * The message under a field — Figma "FormField" (re-read 2026-10-05): 12px
 * Regular on a 16px line. Error is #D80027 with the Warning glyph, success
 * #1FAF38 with CheckCircle: "colour alone must never carry the meaning". A hint
 * is neutral and draws no glyph. Link it to the field with aria-describedby
 * (and aria-invalid for an error); an error is also announced as it appears.
 */
export function FieldMessage({
  id,
  tone = "hint",
  children,
}: {
  id?: string;
  tone?: "hint" | "error" | "success";
  children: React.ReactNode;
}) {
  if (tone === "hint") {
    return (
      <p id={id} className="min-w-0 break-words text-[12px] leading-4 text-[var(--text-secondary)]">
        {children}
      </p>
    );
  }
  const error = tone === "error";
  const Glyph = error ? Warning : CheckCircle;
  return (
    <p
      id={id}
      role={error ? "alert" : "status"}
      className={`flex min-w-0 items-start gap-1 break-words text-[12px] leading-4 [overflow-wrap:anywhere] ${
        error ? "text-[var(--accent-danger)]" : "text-[var(--accent-success)]"
      }`}
    >
      <Glyph size={16} weight="fill" aria-hidden="true" className="shrink-0" />
      <span className="min-w-0">{children}</span>
    </p>
  );
}

export default FieldMessage;
