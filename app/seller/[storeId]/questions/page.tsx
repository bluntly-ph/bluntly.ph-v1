import { SellerQuestions } from "@/components/seller/console/SellerQuestions";
import { flatParams } from "@/components/console/list-query";
import { getStoreQuestions } from "@/lib/seller-console";

/** Screen/Seller/Questions (Figma 8196:21469). The layout has already checked ownership. */
export default async function SellerQuestionsPage({
  params,
  searchParams,
}: {
  params: Promise<{ storeId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { storeId } = await params;
  const sp = await searchParams;
  const asked = sp.answer;
  const query = flatParams(sp, ["sort", "community", "q"]);
  const tab = sp.tab === "answered" || sp.tab === "all" ? sp.tab : "unanswered";
  const answerTo = typeof asked === "string" && asked ? asked : null;
  const questions = await getStoreQuestions(storeId);
  if (questions === null) {
    return (
      <p role="alert" className="py-10 text-center text-[14px] text-[var(--text-secondary)]">
        Your questions could not be loaded. Nothing has changed; try again in a moment.
      </p>
    );
  }
  // eslint-disable-next-line react-hooks/purity -- a server render's clock, read once.
  const now = Date.now();
  // Keyed on the query: a new sort or filter starts on page 1 (the tab is in the URL too).
  return (
    <SellerQuestions key={JSON.stringify(query)} questions={questions} now={now} answerTo={answerTo} storeId={storeId} initialTab={tab} query={query} />
  );
}
