import type { Metadata } from "next";

import { NewMessageForm } from "@/components/messages/NewMessageForm";
import { MessagesNav } from "@/components/messages/ReviewerMessages";
import type { Topic } from "@/components/messages/messages-model";
import { SiteHeader } from "@/components/site/SiteHeader";
import { requireOnboardedUser } from "@/lib/dal";
import { getLinkOptions } from "@/lib/messages";

export const metadata: Metadata = { title: "New message — bluntly" };

const TOPICS = new Set(["payout", "review", "report", "account", "other"]);

/**
 * Screen/Messages/New (Figma 8296:31389, error 8313:31919) with
 * Sheet/Messages/Link (8313:32096). ?topic= and ?link= preselect, so a failed
 * payout or a removed review can open this already linked.
 */
export default async function NewMessagePage({ searchParams }: { searchParams: Promise<{ topic?: string; link?: string }> }) {
  const me = await requireOnboardedUser();
  const sp = await searchParams;
  const options = await getLinkOptions("reviewer");
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-card)]">
      <div className="hidden md:block">
        <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      </div>
      <div className="md:hidden">
        <MessagesNav backHref="/messages" avatarUrl={me.avatar_url ?? null} name={me.display_name ?? me.username ?? "You"} />
      </div>
      <main className="mx-auto flex w-full max-w-[480px] flex-1 flex-col gap-5 px-4 pb-6 pt-2 md:pt-8">
        <div className="flex flex-col gap-2">
          <h1 className="text-[24px] font-semibold leading-none">New message</h1>
          <p className="text-[14px] text-[var(--text-secondary)]">To the Bluntly team</p>
        </div>
        <NewMessageForm
          audience="reviewer"
          options={options}
          initialTopic={sp.topic && TOPICS.has(sp.topic) ? (sp.topic as Topic) : undefined}
          initialLink={sp.link}
          doneHref="/messages/:id"
        />
      </main>
    </div>
  );
}
