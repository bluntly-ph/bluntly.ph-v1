"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { FIELD_INPUT } from "@/components/console/fields";
import { Callout } from "@/components/console/Callout";
import { Switch } from "@/components/console/Switch";

/**
 * Overlay/Settings/ConnectPayMongo (Figma 8237:25540): the PayMongo keys, the
 * payout methods to offer and test mode, saved by a Super Admin through
 * PUT /admin/integrations/paymongo. The secret key is encrypted on the server
 * and never comes back (only "sk_test_…1234"); "Test connection" makes one
 * read-only call with it.
 *
 * Saving keys sends no money: nothing pays out through PayMongo, payouts stay
 * manual (owner decision; automatic transfers are separate, unbuilt work).
 * Without INTEGRATION_SECRETS_KEY on the server nothing can be saved, and the
 * overlay says so.
 */

type Config = import("@/lib/api-types").components["schemas"]["PayMongoConfigOut"];
type Method = "gcash" | "maya" | "bank";
const METHODS: { key: Method; label: string }[] = [
  { key: "gcash", label: "GCash" },
  { key: "maya", label: "Maya" },
  { key: "bank", label: "Bank transfer" },
];

export function ConnectPayMongoButton({ connected, canEdit }: { connected: boolean; canEdit: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="flex h-8 items-center rounded-full border border-[var(--text-primary)] px-3 text-[12px]">
        {connected ? "Manage" : "Connect"}
      </button>
      {open ? <ConnectPayMongoDialog canEdit={canEdit} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

async function problem(res: Response, fallback: string): Promise<string> {
  const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
  return typeof p.detail === "string" ? p.detail : fallback;
}

function ConnectPayMongoDialog({ canEdit, onClose }: { canEdit: boolean; onClose: () => void }) {
  const router = useRouter();
  const [config, setConfig] = useState<Config | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [publicKey, setPublicKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [methods, setMethods] = useState<Method[]>(["gcash", "maya"]);
  const [testMode, setTestMode] = useState(true);
  const [busy, setBusy] = useState<null | "save" | "test" | "remove">(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  function apply(c: Config) {
    setConfig(c);
    if (c.connected) {
      setPublicKey(c.public_key ?? "");
      setMethods(c.methods as Method[]);
      setTestMode(c.test_mode);
    }
  }

  useEffect(() => {
    let live = true;
    fetch("/api/bff/api/v1/admin/integrations/paymongo", { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<Config>) : Promise.reject(new Error("load"))))
      .then((c) => {
        if (live) apply(c);
      })
      .catch(() => live && setLoadFailed(true));
    return () => {
      live = false;
    };
  }, []);

  async function call(kind: "save" | "test" | "remove") {
    setBusy(kind);
    setError(null);
    setSaved(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/integrations/paymongo${kind === "test" ? "/test" : ""}`, {
        method: kind === "save" ? "PUT" : kind === "test" ? "POST" : "DELETE",
        headers: kind === "save" ? { "content-type": "application/json" } : undefined,
        body: kind === "save" ? JSON.stringify({ public_key: publicKey.trim(), secret_key: secretKey.trim() || null, methods, test_mode: testMode }) : undefined,
      });
      if (!res.ok) {
        setError(await problem(res, kind === "test" ? "The test couldn’t run." : "That didn’t save."));
        return;
      }
      const c = (await res.json()) as Config;
      apply(c);
      setSecretKey("");
      if (kind === "remove") {
        setPublicKey("");
        setSaved("Keys removed.");
      } else if (kind === "save") {
        setSaved("Saved. No money moves: payouts stay manual.");
      }
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(null);
    }
  }

  const ready = Boolean(config?.storage_ready);
  const editable = canEdit && ready;
  const mode = testMode ? "test" : "live";
  const LABEL = "mb-1.5 block text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--text-secondary)]";
  const FIELD = FIELD_INPUT;
  const canSave = editable && publicKey.trim().length >= 8 && methods.length > 0 && (Boolean(secretKey.trim()) || Boolean(config?.connected));
  const last = config?.last_test;

  return (
    <AdminModal title="Connect PayMongo" width={560} onClose={onClose}>
      <div className="flex flex-col gap-4 px-6 pb-5 pt-4">
        {loadFailed ? (
          <p role="alert" className="text-[13px] text-[var(--accent-danger)]">
            The PayMongo settings couldn’t be loaded.
          </p>
        ) : config && !ready ? (
          <p role="status" className="flex items-start gap-2 rounded-[12px] bg-[var(--status-high-bg)] px-4 py-3 text-[13px] text-[var(--status-high-fg)]">
            <WarningCircle size={18} weight="fill" aria-hidden className="mt-px shrink-0" />
            Keys can’t be stored on this server yet: INTEGRATION_SECRETS_KEY isn’t set. Nothing can be saved.
          </p>
        ) : null}
        <p className="text-[14px]">Send payouts to GCash, Maya and bank accounts automatically. Each batch still waits for an admin to approve it.</p>
        <div>
          <label htmlFor="pm-public" className={LABEL}>
            Public key
          </label>
          <input id="pm-public" disabled={!editable} placeholder={`pk_${mode}_…`} autoComplete="off" value={publicKey} onChange={(e) => setPublicKey(e.target.value)} className={FIELD} />
        </div>
        <div>
          <label htmlFor="pm-secret" className={LABEL}>
            Secret key
          </label>
          <input
            id="pm-secret"
            type="password"
            disabled={!editable}
            placeholder={config?.secret_hint ? `${config.secret_hint} saved · leave blank to keep` : `sk_${mode}_…`}
            autoComplete="off"
            value={secretKey}
            onChange={(e) => setSecretKey(e.target.value)}
            className={FIELD}
          />
        </div>
        <div>
          <p className={LABEL}>Payout methods</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Payout methods">
            {METHODS.map((m) => {
              const on = methods.includes(m.key);
              return (
                <button
                  key={m.key}
                  type="button"
                  aria-pressed={on}
                  disabled={!editable}
                  onClick={() => setMethods((list) => (on ? list.filter((x) => x !== m.key) : [...list, m.key]))}
                  className={`rounded-full border px-4 py-[7px] text-[14px] disabled:opacity-60 ${on ? "border-[var(--base-ink-800)] bg-[var(--base-ink-800)] text-white" : "border-[var(--border-subtle)]"}`}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-[12px] bg-[var(--surface-app)] px-4 py-3">
          <span className="flex flex-1 flex-col gap-1 leading-none">
            <span className="text-[14px] font-medium" id="pm-test-label">
              Test mode
            </span>
            <span className="text-[12px] text-[var(--text-secondary)]">Use test keys first. No money moves.</span>
          </span>
          <Switch checked={testMode} onChange={setTestMode} labelledBy="pm-test-label" disabled={!editable} />
        </div>
        <Callout>
          Keys are stored encrypted. Only Super Admins can change them. Saving keys sends no money: automatic payouts aren’t built, so payouts stay manual.
        </Callout>
        {last ? (
          <p role="status" className={`flex items-center gap-2 text-[12px] ${last.ok ? "text-[var(--accent-success)]" : "text-[var(--accent-danger)]"}`} suppressHydrationWarning>
            {last.ok ? <CheckCircle size={14} weight="fill" aria-hidden /> : <WarningCircle size={14} weight="fill" aria-hidden />}
            {last.detail} · tested {new Date(last.at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Manila" })}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
        {saved ? (
          <p role="status" className="text-[12px] text-[var(--accent-success)]">
            {saved}
          </p>
        ) : null}
        {!canEdit ? <p className="text-[12px] text-[var(--text-secondary)]">You can see the settings; only a Super Admin can change them.</p> : null}
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
          {config?.connected ? "Close" : "Cancel"}
        </button>
        {config?.connected && canEdit ? (
          <>
            <button type="button" disabled={busy !== null} onClick={() => void call("test")} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px] disabled:opacity-50">
              {busy === "test" ? "Testing…" : "Test connection"}
            </button>
            <button type="button" disabled={busy !== null} onClick={() => void call("remove")} className="h-9 rounded-full px-3 text-[12px] text-[var(--accent-danger)] disabled:opacity-50">
              {busy === "remove" ? "Removing…" : "Remove keys"}
            </button>
          </>
        ) : null}
        <span className="flex-1" />
        <button type="button" disabled={!canSave || busy !== null} onClick={() => void call("save")} className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50">
          {busy === "save" ? "Saving…" : config?.connected ? "Save changes" : "Connect"}
        </button>
      </div>
    </AdminModal>
  );
}
