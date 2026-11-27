import Link from "next/link";

export type Interaction = {
  user_id: string;
  username: string | null;
  display_name: string | null;
  upvotes: number;
  downvotes: number;
  comments: number;
};

/**
 * Business Rules §17: who this person engages with most, and who engages with
 * them. Public on every profile, and deliberately limited to counts of votes
 * and comments — never who reported whom, and never money.
 */
export function InteractionLists({
  name,
  withMost,
  byMost,
}: {
  name: string;
  withMost: Interaction[];
  byMost: Interaction[];
}) {
  if (withMost.length === 0 && byMost.length === 0) return null;
  return (
    <section aria-label="Interactions" className="mt-8 grid gap-6 px-4 md:grid-cols-2 md:px-0">
      <List title={`${name} interacts most with`} rows={withMost} />
      <List title={`Interacts most with ${name}`} rows={byMost} />
    </section>
  );
}

function List({ title, rows }: { title: string; rows: Interaction[] }) {
  return (
    <div>
      <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">{title}</h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-[12px] text-[var(--text-secondary)]">No one yet.</p>
      ) : (
        <ol className="mt-2 flex flex-col gap-1.5">
          {rows.map((r) => (
            <li key={r.user_id} className="flex flex-wrap items-baseline gap-x-2 text-[13px]">
              <Link
                href={`/u/${r.username ?? r.user_id}`}
                className="font-medium text-[var(--text-primary)] underline-offset-4 hover:underline [overflow-wrap:anywhere]"
              >
                {r.username ?? r.display_name ?? "member"}
              </Link>
              <span className="text-[12px] text-[var(--text-secondary)]">
                {[
                  r.upvotes ? `${r.upvotes} up` : null,
                  r.downvotes ? `${r.downvotes} down` : null,
                  r.comments ? `${r.comments} comment${r.comments === 1 ? "" : "s"}` : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
