"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { CaretDown, CaretRight, Check, LinkSimple, Paperclip, X } from "@phosphor-icons/react/dist/ssr";

import { countProblem, countState } from "@/components/console/counted-model";

import { FIRST_MAX, REVIEWER_TOPICS, SELLER_TOPICS, type Topic } from "./messages-model";
import { PUBLIC_SELECT } from "@/components/ui/field-styles";

/**
 * A new conversation with the Bluntly team, in the two shapes the Figma draws:
 *
 * - "seller": Overlay/Store/Chat/New (8276:29363) — About (Menu/Store/Chat/Topic
 *   8276:29564), Which one (Menu/Store/Chat/Appeal 8287:29845), Message,
 *   Attach a file, Cancel / Send; error state 8314:33626.
 * - "reviewer": Screen/Messages/New (8296:31389) — topic chips, "Linked to
 *   (optional)" opening Sheet/Messages/Link (8313:32096), Message, Attach a
 *   screenshot, Send; error state 8313:31919.
 *
 * Links offered are the member's own (GET /conversations/link-options); the
 * API checks them again. On success the member lands in the new thread.
 */

type Schemas = import("@/lib/api-types").components["schemas"];
type LinkOption = Schemas["LinkOptionOut"];

export function NewMessageForm({
  audience,
  sellerId,
  options,
  initialTopic,
  initialLink,
  onCancel,
  onDone,
  doneHref,
}: {
  audience: "seller" | "reviewer";
  sellerId?: string;
  options: LinkOption[];
  initialTopic?: Topic;
  initialLink?: string;
  onCancel?: () => void;
  /** Called once the conversation exists (the seller overlay closes itself). */
  onDone?: () => void;
  /** Where the new conversation opens; ":id" is replaced by its id. A string,
   *  not a function, so a server page can pass it. */
  doneHref: string;
}) {
  const router = useRouter();
  const topics = audience === "seller" ? SELLER_TOPICS : REVIEWER_TOPICS;
  const preset = initialLink ? options.find((o) => o.id === initialLink) : undefined;
  const [topic, setTopic] = useState<Topic>((preset?.topic as Topic) ?? initialTopic ?? topics[0].key);
  const [link, setLink] = useState<string>(preset?.id ?? "");
  const [body, setBody] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [emptyTried, setEmptyTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const linkType = topics.find((t) => t.key === topic)?.link;
  const choices = linkType ? options.filter((o) => o.type === linkType) : [];
  const required = topic === "claim";
  const chosen = choices.find((o) => o.id === link) ?? null;
  const empty = !body.trim();
  const count = countState(body, FIRST_MAX);
  const problem = emptyTried && empty ? "Write a message before sending." : countProblem(count);

  function pickTopic(next: Topic) {
    setTopic(next);
    if (!options.some((o) => o.id === link && o.topic === next)) setLink("");
  }

  async function send() {
    if (empty) {
      setEmptyTried(true);
      return;
    }
    if (count.over) return;
    if (required && !chosen) {
      setError("Choose the claim this is about.");
      return;
    }
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("audience", audience);
    form.append("topic", topic);
    form.append("body", body.trim());
    if (sellerId) form.append("seller_id", sellerId);
    if (chosen) {
      form.append("link_type", chosen.type);
      form.append("link_id", chosen.id);
    }
    if (file) form.append("file", file);
    try {
      const res = await fetch("/api/bff/api/v1/conversations", { method: "POST", body: form });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "Your message wasn’t sent.");
        return;
      }
      const conv = (await res.json()) as { id: string };
      onDone?.();
      router.push(doneHref.replace(":id", encodeURIComponent(conv.id)));
      router.refresh();
    } catch {
      setError("You’re offline. Try again when you’re back online.");
    } finally {
      setBusy(false);
    }
  }

  const LABEL = "mb-2 block text-[14px] font-medium";
  const counter = (
    <span
      className={`pointer-events-none absolute bottom-3 right-4 text-[12px] [font-variant-numeric:tabular-nums] ${
        count.over ? "font-medium text-[var(--accent-danger)]" : "text-[var(--text-secondary)]"
      }`}
    >
      {count.label}
    </span>
  );
  const message = (
    <div>
      <label htmlFor="new-message-body" className={LABEL}>
        Message
      </label>
      <div className="relative">
        <textarea
          id="new-message-body"
          value={body}
          rows={audience === "seller" ? 4 : 4}
          aria-invalid={problem ? true : undefined}
          aria-describedby={problem ? "new-message-empty" : undefined}
          onChange={(e) => setBody(e.target.value)}
          placeholder={audience === "seller" ? "What do you need help with?" : "What happened? Add order numbers or dates if you have them."}
          className={`w-full resize-none rounded-[12px] border px-4 pb-8 pt-3 text-[14px] leading-[21px] outline-none ${
            problem ? "border-[var(--accent-danger)]" : "border-[var(--accent-primary)] focus:border-[var(--accent-primary)]"
          }`}
        />
        {counter}
      </div>
      {problem ? (
        <p id="new-message-empty" aria-live="polite" className="mt-1 text-[12px] text-[var(--accent-danger)]">
          {problem}
        </p>
      ) : null}
    </div>
  );
  const attach = (
    <div className="flex flex-wrap items-center gap-2">
      {file ? (
        <span className="flex items-center gap-2 rounded-full bg-[var(--surface-app)] py-1 pl-3 pr-1 text-[12px]">
          <Paperclip size={14} aria-hidden />
          <span className="max-w-[220px] truncate">{file.name}</span>
          <button type="button" aria-label="Remove attachment" onClick={() => setFile(null)} className="grid size-6 place-items-center rounded-full hover:bg-[var(--surface-card)]">
            <X size={12} />
          </button>
        </span>
      ) : (
        <button type="button" onClick={() => fileInput.current?.click()} className="flex items-center gap-1 text-[12px] font-medium text-[var(--chart-honesty-fund)] hover:underline">
          <LinkSimple size={14} aria-hidden />
          {audience === "seller" ? "Attach a file" : "Attach a screenshot"}
        </button>
      )}
      <input
        ref={fileInput}
        type="file"
        accept="image/png,image/jpeg,image/webp,application/pdf"
        aria-label="Attachment"
        className="hidden"
        onChange={(e) => {
          setFile(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />
    </div>
  );
  const failure = error ? (
    <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
      {error}
    </p>
  ) : null;

  if (audience === "seller") {
    return (
      <>
        <div className="flex flex-col gap-5 overflow-y-auto px-6 pb-5 pt-4">
          <div>
            <label htmlFor="new-message-topic" className={LABEL}>
              About
            </label>
            <SelectBox id="new-message-topic" value={topic} onChange={(v) => pickTopic(v as Topic)} options={topics.map((t) => [t.key, t.label])} />
          </div>
          {linkType === "appeal" || linkType === "claim" ? (
            <div>
              <label htmlFor="new-message-link" className={LABEL}>
                Which one
              </label>
              <SelectBox
                id="new-message-link"
                value={link}
                onChange={setLink}
                placeholder={choices.length ? `Choose ${linkType === "appeal" ? "an appeal" : "a claim"}` : `You have no ${linkType}s yet`}
                options={choices.map((o) => [o.id, o.sublabel ? `${o.label} · ${o.sublabel}` : o.label])}
              />
              <p className="mt-2 text-[12px] text-[var(--text-secondary)]">
                {required ? "Required. The team sees the claim’s details." : "Optional. Links the conversation so the team sees the details."}
              </p>
            </div>
          ) : null}
          {message}
          {attach}
          {failure}
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
          <button type="button" onClick={onCancel} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
            Cancel
          </button>
          <button type="button" disabled={busy || count.over} onClick={() => void send()} className="h-9 rounded-full bg-[var(--accent-primary)] px-5 text-[12px] text-white disabled:opacity-60">
            {busy ? "Sending…" : "Send"}
          </button>
        </div>
      </>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-5">
      <fieldset>
        <legend className={LABEL}>What is it about?</legend>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="What is it about?">
          {topics.map((t) => (
            <button
              key={t.key}
              type="button"
              role="radio"
              aria-checked={topic === t.key}
              onClick={() => pickTopic(t.key)}
              className={`rounded-full border px-3 py-[7px] text-[12px] ${
                topic === t.key ? "border-[var(--accent-primary)] bg-[var(--status-high-bg)] text-[var(--accent-primary)]" : "border-[var(--border-subtle)] hover:border-[var(--text-secondary)]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </fieldset>
      {linkType ? (
        <div>
          <p className={LABEL}>Linked to (optional)</p>
          <button
            type="button"
            onClick={() => setSheet(true)}
            aria-haspopup="dialog"
            className="flex w-full items-center gap-3 rounded-[12px] border border-[var(--border-subtle)] px-4 py-3 text-left text-[14px] hover:border-[var(--text-secondary)]"
          >
            <span className="min-w-0 flex-1 truncate">{chosen ? `${chosen.label}${chosen.sublabel ? ` · ${chosen.sublabel}` : ""}` : "Nothing in particular"}</span>
            <CaretRight size={16} aria-hidden />
          </button>
        </div>
      ) : null}
      {message}
      {attach}
      {failure}
      <span className="flex-1" />
      <button type="button" disabled={busy || count.over} onClick={() => void send()} className="h-12 w-full rounded-full bg-[var(--accent-primary)] text-[16px] font-medium text-white disabled:opacity-60">
        {busy ? "Sending…" : "Send"}
      </button>
      {sheet ? (
        <LinkSheet
          options={options}
          value={link}
          onPick={(o) => {
            setSheet(false);
            if (!o) {
              setLink("");
              return;
            }
            setLink(o.id);
            setTopic(o.topic as Topic);
          }}
          onClose={() => setSheet(false)}
        />
      ) : null}
    </div>
  );
}

function SelectBox({
  id,
  value,
  onChange,
  options,
  placeholder,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-empty={value ? undefined : true}
        className={`${PUBLIC_SELECT} data-[empty=true]:text-[var(--text-secondary)]`}
      >
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
      <CaretDown size={16} aria-hidden className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2" />
    </div>
  );
}

/** Sheet/Messages/Link (8313:32096): the member's own payouts, reviews and reports. */
function LinkSheet({
  options,
  value,
  onPick,
  onClose,
}: {
  options: LinkOption[];
  value: string;
  onPick: (o: LinkOption | null) => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center" role="dialog" aria-modal="true" aria-label="Link it to something">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden />
      <div className="relative max-h-[80dvh] w-full max-w-[480px] overflow-y-auto rounded-t-[24px] bg-[var(--surface-card)] px-4 pb-6 pt-3">
        <span aria-hidden className="mx-auto mb-3 block h-1 w-10 rounded-full bg-[var(--border-subtle)]" />
        <h2 className="mb-2 text-[16px] font-semibold">Link it to something</h2>
        <ul className="flex flex-col">
          {options.map((o) => (
            <li key={o.id}>
              <button type="button" onClick={() => onPick(o)} className="flex w-full items-center gap-3 border-b border-[var(--border-subtle)] py-3 text-left">
                <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
                  <span className="truncate text-[14px]">{o.label}</span>
                  {o.sublabel ? <span className="truncate text-[12px] text-[var(--text-secondary)]">{o.sublabel}</span> : null}
                </span>
                {value === o.id ? <Check size={16} aria-hidden /> : null}
              </button>
            </li>
          ))}
          <li>
            <button type="button" onClick={() => onPick(null)} className="flex w-full items-center gap-3 py-3 text-left">
              <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
                <span className="text-[14px]">Nothing in particular</span>
                <span className="text-[12px] text-[var(--text-secondary)]">General question</span>
              </span>
              {value === "" ? <Check size={16} aria-hidden /> : null}
            </button>
          </li>
        </ul>
      </div>
    </div>
  );
}
