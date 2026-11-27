import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { requireOnboardedUser } from "@/lib/dal";
import { getProductSummary } from "@/lib/products";
import { getReviewFull } from "@/lib/reviews";
import { getSessionToken } from "@/lib/session";

import { WriteReviewForm, type UpdateOf } from "./WriteReviewForm";

export const metadata: Metadata = {
  title: "Write a review — bluntly",
};

export default async function NewReviewPage({
  searchParams,
}: {
  searchParams: Promise<{ update?: string | string[]; product?: string | string[] }>;
}) {
  // Writing requires an account; requireUser redirects to /login otherwise.
  const me = await requireOnboardedUser();

  // `?update=<review id>`: a dated update entry on the reviewer's own thread
  // (Business Rules §4). The product is the thread's, so it is read here and
  // fixed; the cooldown itself is the API's to enforce on submit.
  const { update: raw, product: productParam } = await searchParams;
  const updateId = typeof raw === "string" ? raw : null;
  let update: UpdateOf | null = null;
  if (updateId) {
    const full = await getReviewFull(updateId, await getSessionToken());
    if (!full || !full.product || full.author?.id !== me.id) notFound();
    update = {
      reviewId: updateId,
      product: {
        id: full.product.id,
        canonical_name: full.product.canonical_name,
        category: full.product.category,
        image_url: full.product.image_url,
      },
    };
  }

  // `?product=<id>`: "Answer with a review" on a request opens the composer on
  // the request's product (dev/QA sync 2026-09-29). An unknown id just asks.
  const initialProduct =
    !update && typeof productParam === "string" ? await getProductSummary(productParam) : null;

  return (
    // No SiteHeader: the reviewer frames draw a composer-specific header — a
    // back arrow and the avatar — and the form owns it, because only the form
    // knows what "back" means at each step.
    <div className="flex min-h-dvh flex-col">
      <WriteReviewForm
        user={{
          username: me.username,
          avatarUrl: me.avatar_url,
          role: me.role,
          reputationScore: me.reputation_score,
          trustStage: me.trust_stage,
          trustLevelName: me.trust_level_name,
        }}
        ownerId={me.id}
        update={update}
        initialProduct={initialProduct}
      />
    </div>
  );
}
