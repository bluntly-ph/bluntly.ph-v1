"use client";

import { useId } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";

import { FieldMessage } from "@/components/ui/FieldMessage";
import { PUBLIC_FIELD_STACK, PUBLIC_FILL, PUBLIC_INPUT_UNFILLED, PUBLIC_LABEL } from "@/components/ui/field-styles";

/**
 * Text input with its label and message — Figma "TextField" (6808:456) inside
 * "FormField", re-read 2026-10-05. Every state is drawn by the shared classes
 * in field-styles.ts: Default, Hover, Focus, Filled, Error (aria-invalid),
 * Success (data-valid), Disabled, read-only.
 *
 * The component set snapped the gradient auth screens' 52px field to the 48px
 * system height and 16px value, and normalised UsernameField the same way
 * ("components are the source of truth"). `tone="soft"` keeps those screens'
 * white-at-30% fill — the description calls the translucent treatment an open
 * decision, so it stays as built — with every state's border still drawn.
 *
 * The design shows only placeholder text inside the field. A placeholder is not
 * an accessible name and vanishes on focus, so a real <label> is always
 * rendered; where the frame shows no visible label the caller passes
 * `labelHidden` and it stays available to assistive tech only.
 */

export type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "className" | "size"> & {
  label: string;
  labelHidden?: boolean;
  error?: string;
  /** A positive check (e.g. "@name is available."): the Success state. */
  success?: string;
  hint?: string;
  adornment?: ReactNode;
  tone?: "outline" | "soft";
};

export function TextField({
  label,
  labelHidden = false,
  error,
  success,
  hint,
  adornment,
  tone = "outline",
  required,
  ...rest
}: TextFieldProps) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? success ?? hint;
  const soft = tone === "soft";

  return (
    <div className={PUBLIC_FIELD_STACK}>
      <label htmlFor={id} className={labelHidden ? "sr-only" : PUBLIC_LABEL}>
        {label}
      </label>

      <div className="relative flex items-center">
        {adornment ? (
          <span
            className="pointer-events-none absolute left-4 flex items-center text-[16px] text-[var(--text-muted)]"
            aria-hidden="true"
          >
            {adornment}
          </span>
        ) : null}
        <input
          id={id}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={message ? messageId : undefined}
          data-valid={!error && success ? true : undefined}
          className={[
            PUBLIC_INPUT_UNFILLED,
            // The soft fill is the gradient screens' translucent white; on the
            // desktop card a white field would vanish, so it takes the gray.
            soft ? "bg-[rgba(255,255,255,0.3)]" : PUBLIC_FILL,
            "lg:bg-[var(--surface-input)]",
            adornment ? "pl-11" : "",
          ].join(" ")}
          {...rest}
        />
      </div>

      {error ? (
        <FieldMessage id={messageId} tone="error">
          {error}
        </FieldMessage>
      ) : success ? (
        <FieldMessage id={messageId} tone="success">
          {success}
        </FieldMessage>
      ) : hint ? (
        <FieldMessage id={messageId}>{hint}</FieldMessage>
      ) : null}
    </div>
  );
}

export default TextField;
