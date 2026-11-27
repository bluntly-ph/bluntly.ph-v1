"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";
import { Paperclip, X } from "@phosphor-icons/react";

import { Button } from "@/components/ui/Button";
import { registrationFormatError } from "@/lib/registration-format";
import { PUBLIC_INPUT, PUBLIC_TEXTAREA } from "@/components/ui/field-styles";

/**
 * "Do you run this store?" — a claim REQUEST, never ownership.
 *
 * FR-4 limits seller verification to an administrator cross-checking the store name
 * against the public listing, so submitting here changes nothing on the page:
 * the claim waits in the administrator queue, and the profile reads "Claimed" only
 * after an administrator approves it. The copy says exactly that, so a claimant is
 * not left thinking the badge is broken.
 *
 * Business Rules §9: ownership is proved by a DTI (sole proprietor) or SEC
 * (corporation/partnership) registration, which the administrator cross-checks
 * against the shop name the marketplace shows. And a claim has a cost the
 * claimant should read before sending it: an approved seller account can
 * respond to reviews of its store, but can no longer earn from reviews or have
 * its votes count.
 */
/** Proof files the form takes (MQA-013): what the message bucket accepts. */
const PROOF_TYPES = ["image/png", "image/jpeg", "image/webp", "application/pdf"];
const PROOF_MAX_BYTES = 4 * 1024 * 1024;
const PROOF_MAX_FILES = 3;

export function ClaimSellerForm({
  sellerId,
  signedIn,
  storeName = "",
  myClaim = null,
  underReview = false,
}: {
  sellerId: string;
  signedIn: boolean;
  /** Pre-fills the shop name; the claimant corrects it to the listing's. */
  storeName?: string;
  /** The viewer's own claim on this store that is still waiting (MQA-012). */
  myClaim?: { id: string; created_at: string } | null;
  /** Someone's claim on this store is waiting; the API refuses another. */
  underReview?: boolean;
}) {
  const id = useId();
  const router = useRouter();
  const picker = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [unattached, setUnattached] = useState<string[]>([]);
  const [withdrawing, setWithdrawing] = useState(false);
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"dti" | "sec">("dti");
  const [number, setNumber] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [shopName, setShopName] = useState(storeName);
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!complete || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/sellers/${sellerId}/claims`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          registration_kind: kind,
          registration_number: number.trim(),
          registered_business_name: businessName.trim(),
          marketplace_shop_name: shopName.trim(),
          evidence: evidence.trim() || null,
        }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string; code?: string };
        setError(p.detail ?? "Couldn't send your claim.");
        // Someone else's claim landed first, or this member's own: show the
        // status the page would have shown, not a form that cannot be sent.
        if (p.code === "claim_pending" || p.code === "claim_under_review") router.refresh();
        return;
      }
      const claim = (await res.json()) as { id: string };
      // The proof goes into the claim's own thread, where the administrator
      // reviewing it reads every file (MQA-013). One at a time, so a failure
      // names the file; the claim itself is already in either way.
      const failed: string[] = [];
      for (const file of files) {
        const form = new FormData();
        form.append("audience", "seller");
        form.append("topic", "claim");
        form.append("seller_id", sellerId);
        form.append("link_type", "claim");
        form.append("link_id", claim.id);
        form.append("body", "");
        form.append("file", file);
        const up = await fetch("/api/bff/api/v1/conversations", { method: "POST", body: form }).catch(() => null);
        if (!up?.ok) failed.push(file.name);
      }
      setUnattached(failed);
      setSent(true);
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  // QA-075: the server's own format rule, so Submit is disabled for exactly
  // what the server would refuse. Shown once something has been typed.
  const numberError = registrationFormatError(kind, number);
  const showNumberError = number.trim().length > 0 && numberError !== null;
  const complete =
    numberError === null && businessName.trim().length >= 2 && shopName.trim().length >= 1;

  // Figma TextField (6808:456): every state from the shared public field classes.
  const field = PUBLIC_INPUT;
  const labelCls = "flex flex-col gap-1.5 text-[13px] font-medium text-[var(--text-primary)]";

  const pill =
    "mt-4 inline-flex h-9 cursor-pointer items-center rounded-[var(--radius-pill)] border border-[var(--base-gray-600)] px-4 text-[14px] text-[var(--text-primary)] no-underline hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)]";

  if (!signedIn) {
    return (
      <Link href="/login" className={pill}>
        Log in to claim this store
      </Link>
    );
  }

  const note =
    "mt-4 rounded-[var(--radius-sm)] bg-[color-mix(in_srgb,var(--accent-trust)_12%,transparent)] px-4 py-3 text-[13px] text-[var(--text-primary)]";

  if (sent) {
    return (
      <div role="status" className={note}>
        <p>
          Your claim is in{files.length > unattached.length ? `, with ${files.length - unattached.length} file${files.length - unattached.length === 1 ? "" : "s"} attached` : ""}.
          An administrator will check your registration against the shop name on the listing, and this
          page will show the store as claimed only once they approve it. Their questions arrive in{" "}
          <Link href="/messages" className="underline underline-offset-4">Messages</Link>.
        </p>
        {unattached.length ? (
          <div className="mt-2 text-[var(--accent-danger)]">
            <p>
              {unattached.length === 1 ? "This file wasn’t attached" : "These files weren’t attached"}. Your claim
              is in; send {unattached.length === 1 ? "it" : "them"} from Messages.
            </p>
            <ul className="mt-1 list-disc pl-5 [overflow-wrap:anywhere]">
              {unattached.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    );
  }

  // MQA-012: the viewer's own claim is waiting - its status, not a second form.
  if (myClaim) {
    const sentOn = new Date(myClaim.created_at).toLocaleDateString("en-PH", { dateStyle: "medium" });
    return (
      <div role="status" className={note}>
        <p className="font-medium">Your claim is being reviewed</p>
        <p className="mt-1 text-[var(--text-secondary)]">
          Sent {sentOn}. An administrator checks your registration against the shop name on the listing;
          questions and requests for documents arrive in Messages.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Link href="/messages" className="underline underline-offset-4">Open Messages</Link>
          <button
            type="button"
            disabled={withdrawing}
            onClick={async () => {
              setWithdrawing(true);
              const res = await fetch(`/api/bff/api/v1/sellers/claims/${myClaim.id}/withdraw`, { method: "POST" }).catch(() => null);
              setWithdrawing(false);
              if (res?.ok) router.refresh();
              else setError("Couldn't withdraw the claim. Try again.");
            }}
            className="cursor-pointer text-[var(--text-secondary)] underline-offset-4 hover:underline disabled:cursor-wait"
          >
            {withdrawing ? "Withdrawing…" : "Withdraw claim"}
          </button>
        </div>
        {error ? <p role="alert" className="mt-2 text-[var(--accent-danger)]">{error}</p> : null}
      </div>
    );
  }

  // Another member's claim is waiting: the API takes no second one until it is decided.
  if (underReview) {
    return (
      <div role="status" className={note}>
        <p className="font-medium">A claim on this store is being reviewed</p>
        <p className="mt-1 text-[var(--text-secondary)]">
          If you run this store, <Link href="/messages/new?topic=account" className="underline underline-offset-4">message the Bluntly team</Link>{" "}
          and an administrator will look at both.
        </p>
      </div>
    );
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className={pill}>
        Claim this store
      </button>
    );
  }

  return (
    <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
      <fieldset className="flex flex-col gap-2">
        <legend className="text-[13px] font-medium text-[var(--text-primary)]">Business registration</legend>
        <div className="flex flex-wrap gap-4 text-[13px] text-[var(--text-primary)]">
          <label className="inline-flex cursor-pointer items-center gap-2">
            <input type="radio" name={`${id}-kind`} checked={kind === "dti"} onChange={() => setKind("dti")} />
            DTI (sole proprietor)
          </label>
          <label className="inline-flex cursor-pointer items-center gap-2">
            <input type="radio" name={`${id}-kind`} checked={kind === "sec"} onChange={() => setKind("sec")} />
            SEC (corporation or partnership)
          </label>
        </div>
      </fieldset>
      <label className={labelCls}>
        {kind === "dti" ? "DTI business name registration number" : "SEC registration number"}
        <input
          value={number}
          onChange={(e) => setNumber(e.target.value.slice(0, 64))}
          autoComplete="off"
          inputMode={kind === "dti" ? "numeric" : "text"}
          placeholder={kind === "dti" ? "e.g. 3318207" : "e.g. CS201012345"}
          aria-invalid={showNumberError}
          aria-describedby={`${id}-number-help`}
          className={field}
        />
        <span
          id={`${id}-number-help`}
          className={`text-[12px] font-normal ${showNumberError ? "text-[var(--accent-danger)]" : "text-[var(--text-secondary)]"}`}
        >
          {showNumberError
            ? numberError
            : "We check the format only. An administrator checks the registration itself against your shop."}
        </span>
      </label>
      <label className={labelCls}>
        Registered business name
        <input
          value={businessName}
          onChange={(e) => setBusinessName(e.target.value.slice(0, 200))}
          className={field}
        />
      </label>
      <label className={labelCls}>
        Shop name, exactly as the marketplace shows it
        <input value={shopName} onChange={(e) => setShopName(e.target.value.slice(0, 160))} className={field} />
      </label>
      <label htmlFor={id} className="text-[13px] font-medium text-[var(--text-primary)]">
        Anything else an administrator should know <span className="font-normal text-[var(--text-muted)]">(optional)</span>
      </label>
      <textarea
        id={id}
        value={evidence}
        onChange={(e) => setEvidence(e.target.value.slice(0, 4000))}
        rows={3}
        placeholder="For example: where on the store page your business name appears. Links aren't allowed."
        className={`${PUBLIC_TEXTAREA} resize-y`}
      />
      <div className="flex flex-col gap-1.5">
        <span className="text-[13px] font-medium text-[var(--text-primary)]">
          Proof of registration <span className="font-normal text-[var(--text-muted)]">(optional)</span>
        </span>
        <span className="text-[12px] text-[var(--text-secondary)]">
          Your DTI or SEC certificate or a business permit, as a photo or PDF up to 4 MB, at most {PROOF_MAX_FILES} files.
          The administrator reviewing your claim sees them.
        </span>
        {files.length ? (
          <ul className="flex flex-col gap-1.5">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`} className="flex min-w-0 items-center gap-2 rounded-full bg-[var(--surface-app)] py-1 pl-3 pr-1 text-[12px]">
                <Paperclip size={14} aria-hidden className="shrink-0" />
                <span className="min-w-0 flex-1 truncate" title={f.name}>{f.name}</span>
                <button type="button" aria-label={`Remove ${f.name}`} onClick={() => setFiles(files.filter((_, j) => j !== i))} className="grid size-6 shrink-0 place-items-center rounded-full hover:bg-[var(--surface-card)]">
                  <X size={12} />
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        {files.length < PROOF_MAX_FILES ? (
          <button type="button" onClick={() => picker.current?.click()} className="self-start text-[13px] text-[var(--accent-primary)] underline-offset-4 hover:underline">
            {files.length ? "Add another file" : "Attach a file"}
          </button>
        ) : null}
        <input
          ref={picker}
          type="file"
          accept={PROOF_TYPES.join(",")}
          aria-label="Proof of registration"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (!f) return;
            if (!PROOF_TYPES.includes(f.type)) return setError("Attach a photo (PNG, JPEG or WebP) or a PDF.");
            if (f.size > PROOF_MAX_BYTES) return setError(`${f.name} is over 4 MB.`);
            setError(null);
            setFiles((list) => [...list, f].slice(0, PROOF_MAX_FILES));
          }}
        />
      </div>
      <p className="text-[12px] text-[var(--text-secondary)]">
        Once approved, this becomes a seller account: you can respond publicly to reviews of your
        store and flag ones you believe are fake, but the account can no longer earn from reviews and
        its votes stop counting. Don&rsquo;t upload personal IDs.
      </p>
      {error ? (
        <p role="alert" className="text-[13px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!complete || busy}>
          {busy ? "Sending…" : "Send claim"}
        </Button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="cursor-pointer text-[14px] text-[var(--text-secondary)] underline-offset-4 hover:underline"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export default ClaimSellerForm;
