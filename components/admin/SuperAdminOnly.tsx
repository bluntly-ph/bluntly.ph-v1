import { ShieldCheck } from "@phosphor-icons/react/dist/ssr";

/**
 * What an Administrator sees on a Super Admin section reached by URL (owner
 * decisions C and D). A plain statement rather than a redirect, so a shared
 * link explains itself. The API refuses them regardless (403).
 */
export function SuperAdminOnly({ what }: { what: string }) {
  return (
    <section
      data-testid="super-admin-only"
      className="max-w-[46rem] rounded-[var(--radius-md)] bg-[var(--surface-card)] p-6 shadow-[var(--shadow-card)]"
    >
      <p className="flex items-center gap-2 text-[15px] font-semibold text-[var(--text-primary)]">
        <ShieldCheck size={18} aria-hidden="true" className="text-[var(--accent-primary)]" />
        Super Admin only
      </p>
      <p className="mt-2 text-[13px] leading-relaxed text-[var(--text-secondary)]">
        {what} is a Super Admin&rsquo;s responsibility. Administrators run the operational queues;
        a Super Admin can change your access from User management if you need it.
      </p>
    </section>
  );
}
