import Link from "next/link";

/**
 * Screen/Seller/SellerRules (Figma 8218:23740 and CantDo 8225:24029, Writing
 * 8225:24152, Flagging 8225:24275, Rating 8225:24398, Owning 8225:24521): the
 * frames' copy on one page, each section an anchor of "On this page".
 *
 * Kept to what the platform enforces (checked 2026-10-03): links are refused
 * before posting; phone numbers, emails and chat handles are asked of the
 * store, not machine-blocked, so the page says "don't" rather than "blocked".
 * Responses and store answers can both be edited (0081). Insights, Products and
 * Store profile are not in the console yet, so they are not promised here.
 */

const SECTIONS = [
  ["gives", "What a claim gives you"],
  ["cant", "What you can't do"],
  ["writing", "Writing responses and answers"],
  ["flagging", "Flagging a fake review"],
  ["rating", "How your rating is worked out"],
  ["owning", "Owning a store"],
] as const;

export default async function SellerRulesPage({ params }: { params: Promise<{ storeId: string }> }) {
  const { storeId } = await params;
  const base = `/seller/${storeId}`;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-3">
        <h1 className="flex-1 text-[24px] font-semibold leading-none">Seller rules</h1>
        <span className="text-[12px] text-[var(--text-secondary)]">Updated 1 Oct 2026</span>
      </div>
      <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav aria-label="On this page" className="lg:sticky lg:top-0 lg:self-start">
          <p className="pb-2 text-[12px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]">On this page</p>
          <ul className="flex flex-col gap-1">
            {SECTIONS.map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`} className="block rounded-[10px] px-3 py-2 text-[14px] hover:bg-[var(--surface-app)]">
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex max-w-[720px] flex-col gap-4">
          <Rule id="gives" title="What a claim gives you">
            <p>
              You can respond publicly to reviews of your store, answer questions as the store, flag reviews you think are fake, and see
              figures for your store.
            </p>
            <p className="font-medium">That&rsquo;s everything a claim gives you over a review.</p>
            <Box title="In the console">
              <ul className="flex flex-col gap-2">
                {[
                  ["Reviews", "Respond to buyers in public", `${base}/reviews`],
                  ["Questions", "Answer as the store", `${base}/questions`],
                  ["Appeals", "Follow reviews you flagged", `${base}/appeals`],
                ].map(([t, s, href]) => (
                  <li key={t}>
                    <Link href={href} className="flex flex-col gap-0.5 hover:underline">
                      <span className="font-medium">{t}</span>
                      <span className="text-[12px] text-[var(--text-secondary)]">{s}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Box>
          </Rule>

          <Rule id="cant" title="What you can't do">
            <ul className="list-disc pl-5">
              <li>You can&rsquo;t remove, hide or push down a review.</li>
              <li>You can&rsquo;t vote, write reviews, earn, or be picked as Best Answer, anywhere on Bluntly.</li>
              <li>These limits stay on your account for good.</li>
            </ul>
            <Box title="Why these limits exist">
              Buyers trust Bluntly because stores can&rsquo;t shape what they read. If owners could vote or review, every rating would be in
              question.
            </Box>
          </Rule>

          <Rule id="writing" title="Writing responses and answers">
            <ul className="list-disc pl-5">
              <li>No links of any kind, including shortened or disguised ones: they are refused before posting.</li>
              <li>Don&rsquo;t post phone numbers, emails or chat handles. Keep the conversation on Bluntly.</li>
              <li>Everything you post is public and shows your store name. You can edit it later.</li>
            </ul>
            <Box title="Good">&ldquo;Sorry about the clip, Jun. We&rsquo;ve sent you a replacement, it should arrive this week.&rdquo;</Box>
            <Box title="Refused before posting">&ldquo;See our shop at shp.ee/jisulife&rdquo;</Box>
          </Rule>

          <Rule id="flagging" title="Flagging a fake review">
            <ul className="list-disc pl-5">
              <li>You can flag each review once at a time. Your reason is only seen by admins.</li>
              <li>An admin may ask the reviewer to prove the purchase.</li>
              <li>Upheld: the review is removed. Dismissed: it stays up and you&rsquo;re told why.</li>
              <li>A buyer&rsquo;s order ID is never shown publicly.</li>
            </ul>
            <Box title="How a flag moves">
              <ol className="flex flex-col gap-2">
                {[
                  ["You flag it", "From the review, with a reason"],
                  ["An admin checks", "Your reason and the review"],
                  ["Proof requested", "The reviewer is asked to prove the purchase"],
                  ["Decision", "Removed, or stays up with a reason"],
                ].map(([t, s], i) => (
                  <li key={t} className="flex gap-3">
                    <span className="grid size-6 shrink-0 place-items-center rounded-full bg-[var(--surface-card)] text-[12px]">{i + 1}</span>
                    <span className="flex flex-col gap-0.5">
                      <span className="font-medium">{t}</span>
                      <span className="text-[12px] text-[var(--text-secondary)]">{s}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </Box>
          </Rule>

          <Rule id="rating" title="How your rating is worked out">
            <ul className="list-disc pl-5">
              <li>Overall, customer service and packaging are medians, so a few extreme ratings can&rsquo;t swing them.</li>
              <li>Matched the listing, complete orders and would recommend are shares of reviews.</li>
              <li>Removed reviews don&rsquo;t count.</li>
            </ul>
            <Box title="Example">
              Five ratings: 5, 5, 4, 2 and 1. The median is 4, the middle one. An average would be 3.4, pulled down by one angry rating.
            </Box>
          </Rule>

          <Rule id="owning" title="Owning a store">
            <ul className="list-disc pl-5">
              <li>Ownership is proved with a DTI or SEC registration that matches the shop name on the marketplace.</li>
              <li>A moderator checks every claim. One account owns a store at a time.</li>
            </ul>
            <Box title="What a claim needs">
              <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-x-4 gap-y-2">
                <dt className="font-medium">DTI or SEC registration number</dt>
                <dd className="text-[var(--text-secondary)]">Checked by a moderator, never shown in full</dd>
                <dt className="font-medium">Registered business name</dt>
                <dd className="text-[var(--text-secondary)]">As it appears on your certificate</dd>
                <dt className="font-medium">Shop name on the marketplace</dt>
                <dd className="text-[var(--text-secondary)]">Exactly as buyers see it</dd>
              </dl>
            </Box>
            <p>
              To change any of it,{" "}
              <Link href={`/seller/${storeId}/messages?new=1`} className="text-[var(--chart-honesty-fund)] hover:underline">
                contact support
              </Link>
              .
            </p>
          </Rule>
        </div>
      </div>
    </div>
  );
}

function Rule({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="flex scroll-mt-4 flex-col gap-3 rounded-[16px] border border-[var(--border-subtle)] p-5 text-[14px] leading-[21px]">
      <h2 id={`${id}-h`} className="text-[16px] font-semibold leading-none">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Box({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[12px] bg-[var(--surface-app)] p-4">
      <p className="pb-2 text-[12px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]">{title}</p>
      <div>{children}</div>
    </div>
  );
}
