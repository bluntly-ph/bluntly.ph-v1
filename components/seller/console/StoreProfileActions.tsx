"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CheckCircle, Paperclip, Storefront, XCircle } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { ConfirmDialog, Consequence } from "@/components/admin/ConfirmDialog";
import { countState } from "@/components/console/counted-model";
import { CountedTextarea } from "@/components/console/CountedTextarea";
import { FIELD_INPUT, FIELD_LABEL } from "@/components/console/fields";

import { CHANGE_OPTIONS, changesPayload, changesReady, changesTitle, type ChangeDraft, type ChangeKind } from "./profile-model";

const NOTE_MAX = 300;

/**
 * Overlay/Store/RequestChange (Figma 8209:23626) and Confirm/Store/GiveUp
 * (8220:24024).
 *
 * The store's name and link come from the marketplace and its registration was
 * checked by a moderator, so a change is a request (POST /sellers/{id}/change-
 * requests): one or more changes (MQA-017) in one conversation (MQA-018), each
 * approved or rejected by a moderator, who applies it to the store (MQA-019).
 * Giving the store up is the owner's own call: it only removes their access.
 */
export function RequestChangeButton({
  storeId,
  storeName,
  platform,
  pending = [],
}: {
  storeId: string;
  storeName: string;
  platform: string;
  pending?: ChangeKind[];
}) {
  const [open, setOpen] = useState(false);
  const [giveUp, setGiveUp] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="h-9 shrink-0 rounded-full border border-[var(--text-primary)] px-4 text-[12px] hover:bg-[var(--surface-app)]">
        Request a change
      </button>
      {open ? (
        <RequestChangeDialog
          storeId={storeId}
          platform={platform}
          pending={pending}
          onClose={() => setOpen(false)}
          onGiveUp={() => {
            setOpen(false);
            setGiveUp(true);
          }}
        />
      ) : null}
      <GiveUpDialog storeId={storeId} storeName={storeName} open={giveUp} onClose={() => setGiveUp(false)} />
    </>
  );
}

function RequestChangeDialog({
  storeId,
  platform,
  pending,
  onClose,
  onGiveUp,
}: {
  storeId: string;
  platform: string;
  /** Changes already waiting for a moderator; one open request per change. */
  pending: ChangeKind[];
  onClose: () => void;
  onGiveUp: () => void;
}) {
  const router = useRouter();
  // MQA-017: tick every change this request needs; they go together, in one
  // conversation, and a moderator approves or rejects each.
  const [chosen, setChosen] = useState<ChangeKind[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [regKind, setRegKind] = useState<"dti" | "sec">("dti");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const drafts: ChangeDraft[] = chosen
    .filter((k): k is Exclude<ChangeKind, "give_up"> => k !== "give_up")
    .map((k) => ({ kind: k, value: values[k] ?? "", regKind }));
  const options = CHANGE_OPTIONS.filter((o) => o.kind !== "give_up");

  function toggle(kind: ChangeKind) {
    setError(null);
    setChosen((list) => (list.includes(kind) ? list.filter((k) => k !== kind) : CHANGE_OPTIONS.map((o) => o.kind).filter((k) => k === kind || list.includes(k))));
  }

  async function send() {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("changes", JSON.stringify(changesPayload(drafts)));
    form.append("note", note.trim());
    if (file) form.append("file", file);
    try {
      const res = await fetch(`/api/bff/api/v1/sellers/${encodeURIComponent(storeId)}/change-requests`, { method: "POST", body: form });
      const p = (await res.json().catch(() => ({}))) as { conversation_id?: string; detail?: unknown };
      if (!res.ok || !p.conversation_id) {
        setError(typeof p.detail === "string" ? p.detail : "Your request wasn’t sent.");
        return;
      }
      setSent(p.conversation_id);
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdminModal title="Request a change" width={560} onClose={onClose}>
      {sent ? (
        <div className="flex flex-col gap-3 px-6 pb-5 pt-4">
          <p role="status" className="rounded-[12px] bg-[var(--surface-app)] p-4 text-[14px]">
            Sent: {changesTitle(drafts).toLowerCase()}. A moderator checks each change and answers you in Messages; its status shows on this page.
          </p>
          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
              Close
            </button>
            <Link href={`/seller/${storeId}/messages?c=${sent}`} className="grid h-9 place-items-center rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white">
              Open the message
            </Link>
          </div>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-3 px-6 pb-5 pt-4">
            <p className={FIELD_LABEL} id="change-what">
              What needs changing? Choose all that apply.
            </p>
            <div role="group" aria-labelledby="change-what" className="flex flex-col gap-3">
              {options.map((o) => {
                const on = chosen.includes(o.kind);
                const waiting = pending.includes(o.kind);
                return (
                  <div key={o.kind} className={`rounded-[12px] border px-4 py-3 ${on ? "border-[var(--accent-primary)]" : "border-[var(--border-subtle)]"} ${waiting ? "opacity-60" : ""}`}>
                    <label className={`flex items-center gap-3 ${waiting ? "cursor-not-allowed" : "cursor-pointer"}`}>
                      <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
                        <span className="text-[14px] font-medium">{o.label}</span>
                        <span className="text-[12px] text-[var(--text-secondary)]">{waiting ? "A change is already waiting for a moderator" : o.hint}</span>
                      </span>
                      <input
                        type="checkbox"
                        checked={on}
                        disabled={waiting}
                        onChange={() => toggle(o.kind)}
                        className="size-[18px] shrink-0 accent-[var(--accent-primary)]"
                      />
                    </label>
                    {on && o.field ? (
                      <div className="mt-3 flex flex-col gap-2">
                        {o.kind === "registration" ? (
                          <div role="radiogroup" aria-label="Registration type" className="flex gap-4 text-[13px]">
                            {(["dti", "sec"] as const).map((k) => (
                              <label key={k} className="inline-flex cursor-pointer items-center gap-2">
                                <input type="radio" name="reg-kind" checked={regKind === k} onChange={() => setRegKind(k)} />
                                {k.toUpperCase()}
                              </label>
                            ))}
                          </div>
                        ) : null}
                        <label htmlFor={`change-${o.kind}`} className="sr-only">
                          {o.field}
                        </label>
                        <input
                          id={`change-${o.kind}`}
                          className={FIELD_INPUT}
                          value={values[o.kind] ?? ""}
                          maxLength={o.kind === "link" ? 300 : 160}
                          onChange={(e) => setValues((v) => ({ ...v, [o.kind]: e.target.value }))}
                          placeholder={`${o.field} · ${o.placeholder?.replace("{platform}", platform) ?? ""}`}
                        />
                        <span className="text-[12px] text-[var(--text-secondary)]">{o.note}</span>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
            {chosen.includes("registration") ? (
              <label className="flex cursor-pointer items-center gap-2 self-start rounded-full border border-[var(--border-subtle)] px-3 py-2 text-[12px]">
                <Paperclip size={14} aria-hidden />
                <span className="max-w-[260px] truncate">{file ? file.name : "Attach the certificate (PDF or photo)"}</span>
                <input type="file" accept="application/pdf,image/*" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </label>
            ) : null}
            <CountedTextarea id="change-note" label="Anything else · optional" value={note} onChange={setNote} max={NOTE_MAX} rows={2} />
            {error ? (
              <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
                {error}
              </p>
            ) : null}
            <button type="button" onClick={onGiveUp} className="self-start text-[12px] text-[var(--text-secondary)] underline-offset-4 hover:text-[var(--text-primary)] hover:underline">
              Someone else runs this store now? Give it up instead
            </button>
          </div>
          <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
            <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
              Cancel
            </button>
            <button
              type="button"
              disabled={!changesReady(drafts) || countState(note, NOTE_MAX).over || busy}
              onClick={() => void send()}
              className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50"
            >
              {busy ? "Sending…" : drafts.length > 1 ? `Send ${drafts.length} changes` : "Send request"}
            </button>
          </div>
        </>
      )}
    </AdminModal>
  );
}

export function GiveUpDialog({ storeId, storeName, open, onClose }: { storeId: string; storeName: string; open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/sellers/${encodeURIComponent(storeId)}/give-up`, { method: "POST" });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "The store wasn’t given up. Try again.");
        return;
      }
      router.replace("/seller/dashboard");
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open={open}
      title={`Give up ${storeName}?`}
      confirmLabel="Give up store"
      cancelLabel="Keep it"
      busyLabel="Giving up…"
      busy={busy}
      error={error}
      onConfirm={() => void confirm()}
      onClose={onClose}
    >
      <Consequence icon={<Storefront size={18} aria-hidden />}>You lose responses, answers and analytics for this store.</Consequence>
      <Consequence icon={<CheckCircle size={18} aria-hidden />}>Your past responses and answers stay up.</Consequence>
      <Consequence icon={<XCircle size={18} aria-hidden />}>The limits on voting, reviewing and earning stay on your account.</Consequence>
    </ConfirmDialog>
  );
}
