import { redirect } from "next/navigation";

/**
 * Retired (owner decision 2026-10-03): a store owner writes to the team with
 * New message in the console (Overlay/Store/Chat/New), and an administrator
 * can move a conversation to Queue → Support. Old links land there.
 */
export default async function NewSupportRequestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/seller/${encodeURIComponent(id)}/messages?new=1`);
}
