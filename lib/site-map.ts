/**
 * Every page on bluntly.ph, in one list.
 *
 * It is the answer to "what pages do we have": the source of /sitemap.xml
 * (public pages only), of docs/SITEMAP.md (all of them, with who can open each
 * and where its design comes from), and the list a full-site check walks.
 * tests/frontend/site-map.test.mjs fails if a page exists without an entry, an
 * entry outlives its page, or a declared access level is not what the proxy
 * enforces — so the map cannot quietly go stale.
 *
 * `figma` names the frames a page is built to, from the file's own frame names
 * and node ids. `null` means the file draws no screen for it: a product or
 * business page kept from the PRD and dressed in the Figma system's language.
 *
 * No imports: the test runs this file directly under Node.
 */

export const SITE_URL = "https://www.bluntly.ph";

export type Access =
  /** Anyone, signed in or not. */
  | "public"
  /** Signed-out visitors only; the proxy sends a signed-in reader home. */
  | "signed-out"
  /** Needs a session; the proxy sends a signed-out visitor to /login?next=. */
  | "signed-in"
  /** Needs a session and a staff role: Administrator or Super Admin (app/admin/layout.tsx). */
  | "administrator"
  /** A Super Admin section (owner decisions C/D): user management, 2.5-star routing. */
  | "super-admin"
  /** Needs a session; only the store's approved owner sees its figures. */
  | "store-owner";

export type Group =
  | "Discover"
  | "Community"
  | "Write"
  | "Sign in"
  | "Account"
  | "Earnings"
  | "Company"
  | "Legal"
  | "Administration";

export type SiteRoute = {
  /** The URL pattern, with dynamic segments in brackets as the app names them. */
  path: string;
  /** The page file that serves it. */
  file: string;
  title: string;
  group: Group;
  access: Access;
  purpose: string;
  figma: string | null;
  /** Listed in /sitemap.xml: public, one fixed URL, worth a search engine's time. */
  inSitemap: boolean;
};

export const SITE_ROUTES: SiteRoute[] = [
  // ------------------------------------------------------------------ Discover
  {
    path: "/",
    file: "app/page.tsx",
    title: "Landing",
    group: "Discover",
    access: "public",
    purpose: "The front door: what bluntly is, the ask-anything search, a featured review and the trust story.",
    figma: "Mobile Landing Page (1902:1504)",
    inSitemap: true,
  },
  {
    path: "/search",
    file: "app/search/page.tsx",
    title: "Search",
    group: "Discover",
    access: "public",
    purpose: "Search reviews, questions and sellers in tabs, with filters, sort and recent searches. Has the + action button.",
    figma: "Mobile Search Page for Buyers / Reviewers / Sellers (3481:1776, 3481:1894, 3954:650), All filters, Sort",
    // Not in the sitemap, disallowed in robots.txt and marked noindex: every
    // query is a new URL, so crawling it never ends (app/robots.ts).
    inSitemap: false,
  },
  {
    path: "/categories",
    file: "app/categories/page.tsx",
    title: "Categories",
    group: "Discover",
    access: "public",
    purpose: "Browse every product category; a category opens search filtered to it.",
    figma: "Categories (2355:939), Subcategory (2355:2267)",
    inSitemap: true,
  },
  {
    path: "/feed",
    file: "app/feed/page.tsx",
    title: "Feed",
    group: "Discover",
    access: "public",
    purpose: "The browsing surface for readers who already know bluntly: the latest honest reviews.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/compare",
    file: "app/compare/page.tsx",
    title: "Compare products",
    group: "Discover",
    access: "public",
    purpose: "Side-by-side product comparison, chosen by id in the link (?ids=a,b,c) so it can be shared.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/reviews/[id]",
    file: "app/reviews/[id]/page.tsx",
    title: "Review",
    group: "Discover",
    access: "public",
    purpose: "One review in full: verdict, rating, pros and cons, photos, votes, comments, prices and where to buy.",
    figma: "Review page (4218:1196), More actions, Share to, Shop, Read more",
    inSitemap: false,
  },
  {
    path: "/sellers/[id]",
    file: "app/sellers/[id]/page.tsx",
    title: "Seller",
    group: "Discover",
    access: "public",
    purpose: "A store's page: rating summary, seller reviews and questions. Has the + action button.",
    figma: "Seller Page - Review (4218:2148), Seller Page - Questions (4295:1256), Action Menu (4417:751)",
    inSitemap: false,
  },
  {
    path: "/u/[id]",
    file: "app/u/[id]/page.tsx",
    title: "Public profile",
    group: "Discover",
    access: "public",
    purpose: "A reviewer's public profile: their stats and published reviews.",
    figma: "Profile Page - Reviews / Comments / Stats (5446:4328, 5446:6398, 5446:6532)",
    inSitemap: false,
  },

  // ----------------------------------------------------------------- Community
  {
    path: "/questions",
    file: "app/questions/page.tsx",
    title: "Questions",
    group: "Community",
    access: "public",
    purpose: "Every open question from the community, newest first, with a way to ask one.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/questions/[id]",
    file: "app/questions/[id]/page.tsx",
    title: "Question",
    group: "Community",
    access: "public",
    purpose: "One question with its answers; answer it, or mark the best answer if it is yours.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/questions/[id]/answer",
    file: "app/questions/[id]/answer/page.tsx",
    title: "Answer a question",
    group: "Community",
    access: "signed-in",
    purpose: "The seven-step answer: your words, experience, pros and cons, verdict, fit, rating and a photo.",
    figma: "Answer Page - Step 1..7, All done (7573:8215 to 7573:9158)",
    inSitemap: false,
  },
  {
    path: "/requests",
    file: "app/requests/page.tsx",
    title: "Requests",
    group: "Community",
    access: "public",
    purpose: "The request board (\"Bounty board\" in the menu): products people have asked to see reviewed.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/requests/[id]",
    file: "app/requests/[id]/page.tsx",
    title: "Request",
    group: "Community",
    access: "public",
    purpose:
      "One review request, for good: its product, every review that answers it, and the asker's Best Answer (picked here).",
    figma: null,
    inSitemap: false,
  },

  // --------------------------------------------------------------------- Write
  {
    path: "/reviews/new",
    file: "app/reviews/new/page.tsx",
    title: "Write a review",
    group: "Write",
    access: "signed-in",
    purpose: "The seven-step product review composer, with proof of purchase, the price check and the done screen.",
    figma: "Reviewer Page - Step 1 to Step 7.1, All done (4550:8882), Let's talk money",
    inSitemap: false,
  },
  {
    path: "/sellers/rate",
    file: "app/sellers/rate/page.tsx",
    title: "Rate a seller",
    group: "Write",
    access: "signed-in",
    purpose: "Find or add a store, rate it on four dimensions, write it up; seller reviews go live on posting.",
    figma: "Seller Review - Step 1 to Step 3.3, All done (4652:12914)",
    inSitemap: false,
  },
  {
    path: "/questions/new",
    file: "app/questions/new/page.tsx",
    title: "Ask a question",
    group: "Write",
    access: "signed-in",
    purpose: "Choose who answers (buyers or the seller), pick the product, write the question.",
    figma: "Question Page - Buyer or Seller (4682:14203), Step 1 to Step 3 (4742:15979)",
    inSitemap: false,
  },
  {
    path: "/requests/new",
    file: "app/requests/new/page.tsx",
    title: "Post a request",
    group: "Write",
    access: "signed-in",
    purpose: "Ask for a product to be reviewed.",
    figma: null,
    inSitemap: false,
  },

  // ------------------------------------------------------------------- Sign in
  {
    path: "/welcome",
    file: "app/(auth)/welcome/page.tsx",
    title: "Welcome",
    group: "Sign in",
    access: "signed-out",
    purpose: "The entry screen: continue to sign up or log in.",
    figma: "Login & Signup (5357:2982)",
    inSitemap: false,
  },
  {
    path: "/login",
    file: "app/(auth)/login/page.tsx",
    title: "Log in",
    group: "Sign in",
    access: "signed-out",
    purpose: "Email one-time-code login; returns the reader to the page that sent them (?next=).",
    figma: "Login & Signup (5348:2789 family)",
    inSitemap: false,
  },
  {
    path: "/signup",
    file: "app/(auth)/signup/page.tsx",
    title: "Sign up",
    group: "Sign in",
    access: "signed-out",
    purpose: "Create an account with an emailed one-time code.",
    figma: "Login & Signup (5348:2789 family)",
    inSitemap: false,
  },
  {
    path: "/onboarding",
    file: "app/onboarding/page.tsx",
    title: "Set up your profile",
    group: "Sign in",
    access: "signed-in",
    purpose: "First-run setup: username, profile and interests.",
    figma: "Login & Signup onboarding states, InterestTile (6842:567), StepBar (6820:477)",
    inSitemap: false,
  },

  // ------------------------------------------------------------------- Account
  {
    path: "/profile/edit",
    file: "app/profile/edit/page.tsx",
    title: "Edit your profile",
    group: "Account",
    access: "signed-in",
    purpose: "Change your handle, display name, photo and interests in one form.",
    figma: "No frame — BUSINESS-REQUIRED (BUG-035). The file draws onboarding, which is a different job.",
    inSitemap: false,
  },
  {
    path: "/profile",
    file: "app/profile/page.tsx",
    title: "Your profile",
    group: "Account",
    access: "signed-in",
    purpose: "Your own profile: stats, verified reviews, comments, and sharing it.",
    figma: "Profile Page - Reviews / Comments / Stats (5446:4328, 5446:6398, 5446:6532)",
    inSitemap: false,
  },
  {
    path: "/notifications",
    file: "app/notifications/page.tsx",
    title: "Notifications",
    group: "Account",
    access: "signed-in",
    purpose: "Your account's notifications.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/sellers/[id]/dashboard",
    file: "app/sellers/[id]/dashboard/page.tsx",
    title: "Store dashboard",
    group: "Account",
    access: "store-owner",
    purpose: "Old address of the store dashboard; redirects to the Seller console (/seller/[storeId]).",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/seller/dashboard",
    file: "app/seller/dashboard/page.tsx",
    title: "Seller dashboard",
    group: "Account",
    access: "signed-in",
    purpose: "The claimed seller's way in: opens the Seller console on their first store, or says how to claim one and where a claim in review stands.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]",
    file: "app/seller/[storeId]/page.tsx",
    title: "Seller console — Overview",
    group: "Account",
    access: "store-owner",
    purpose: "The approved owner's Overview: rating tiles for a period, what is waiting on them, rating breakdown, reviews per month, reply rates and recent reviews; store switcher and claim status in the rail.",
    figma: "Screen/Seller/Overview 8190:20643",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/reviews",
    file: "app/seller/[storeId]/reviews/page.tsx",
    title: "Seller console — Reviews",
    group: "Account",
    access: "store-owner",
    purpose: "The store's reviews by Needs response / Responded / All, with sort, filters and search; respond, edit the response, or flag a review as suspected fake.",
    figma: "Screen/Seller/Reviews 8196:20870",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/appeals",
    file: "app/seller/[storeId]/appeals/page.tsx",
    title: "Seller console — Appeals",
    group: "Account",
    access: "store-owner",
    purpose: "The flags the store raised against reviews it believes are fake, In progress / Decided, with where each stands.",
    figma: "Screen/Seller/Appeals 8196:21910",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/questions",
    file: "app/seller/[storeId]/questions/page.tsx",
    title: "Seller console — Questions",
    group: "Account",
    access: "store-owner",
    purpose: "Questions about the store, Unanswered / Answered / All, with answer rate and time to answer; answer as the store.",
    figma: "Screen/Seller/Questions 8196:21469",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/settings",
    file: "app/seller/[storeId]/settings/page.tsx",
    title: "Seller console — Settings",
    group: "Account",
    access: "store-owner",
    purpose: "The owner's account (profile: display name and username), what notifications reach them, and Contact support.",
    figma: "Screen/Seller/Settings 8218:24151",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/rules",
    file: "app/seller/[storeId]/rules/page.tsx",
    title: "Seller console — Seller rules",
    group: "Account",
    access: "store-owner",
    purpose: "What a claim gives a store owner and what it never does: responses, flags, how the store rating is worked out, owning a store.",
    figma: "Screen/Seller/SellerRules 8218:23740",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/products",
    file: "app/seller/[storeId]/products/page.tsx",
    title: "Products (Seller console)",
    group: "Account",
    access: "store-owner",
    purpose: "The product pages the store links to: Linked, Waiting for approval, All; Link a product (a moderator approves), cancel a request, ask for a missing product page; per-product figures.",
    figma: "Screen/Seller/Products 8204:22648, Waiting 8214:23301, All 8214:23647, Loading 8228:26685, Overlay/Store/LinkProduct 8204:23173, Confirm/Store/LinkProduct 8213:23439, Confirm/Store/CancelLink 8213:23484, Overlay/Store/RequestProduct 8213:23372 (+Similar 8278:29593), Menu/Seller/Products/* 8213:*",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/products/[productId]",
    file: "app/seller/[storeId]/products/[productId]/page.tsx",
    title: "Product analytics (Seller console)",
    group: "Account",
    access: "store-owner",
    purpose: "A linked product's figures for its store: median and 30-day change, verdicts, the 6-month trend against its category, recurring pros and cons, category comparisons, recent questions.",
    figma: "Screen/Seller/Products/Analytics 8205:22802",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/insights",
    file: "app/seller/[storeId]/insights/page.tsx",
    title: "Insights (Seller console)",
    group: "Account",
    access: "store-owner",
    purpose: "The store's own reviews over a period: rating, review count against the period before, would recommend, response rate, order facts by month, replies by month and median time to reply, the median store on the same marketplace; Download CSV.",
    figma: "Screen/Seller/Insights 8208:22905, Loading 8228:27172, Overlay/Store/Export 8213:23286, Menu/Store/Period 8212:23210",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/profile",
    file: "app/seller/[storeId]/profile/page.tsx",
    title: "Store profile (Seller console)",
    group: "Account",
    access: "store-owner",
    purpose: "The store as buyers see it, how its claim was verified (registration shown by its last 4 characters only), what owning a store allows, the account's stores; Request a change (sent to the team as a message) and Give up the store.",
    figma: "Screen/Seller/StoreProfile 8209:23011, Loading 8228:27673, Overlay/Store/RequestChange 8209:23626, Confirm/Store/GiveUp 8220:24024",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/public",
    file: "app/seller/[storeId]/public/page.tsx",
    title: "Public page (Seller console)",
    group: "Account",
    access: "store-owner",
    purpose: "The store's public page read inside the console: its figures, reviews (Most helpful, Newest, Lowest rating) with the store's responses, the ratings breakdown and store questions; Open on Bluntly.",
    figma: "Screen/Seller/PublicPage 8217:23574, Loading 8228:28024",
    inSitemap: false,
  },
  {
    path: "/seller/[storeId]/messages",
    file: "app/seller/[storeId]/messages/page.tsx",
    title: "Messages (Seller console)",
    group: "Account",
    access: "store-owner",
    purpose: "The store owner and the Bluntly team: open and closed conversations, New message about an appeal, a claim, a product page or the store, replies (a reply reopens a closed one), attachments.",
    figma: "Screen/Seller/Inbox 8304:32524, Closed 8305:31810, Empty 8314:32768, Loading 8314:32250, Overlay/Store/Chat/New 8276:29363 (+Error 8314:33626), Menu/Store/Chat/Topic 8276:29564, Menu/Store/Chat/Appeal 8287:29845",
    inSitemap: false,
  },
  {
    path: "/messages",
    file: "app/messages/page.tsx",
    title: "Messages",
    group: "Account",
    access: "signed-in",
    purpose: "You and the Bluntly team: open and closed conversations about a payout, a review you wrote, a report you made or your account.",
    figma: "Screen/Messages 8296:31219, Empty 8296:31548, Closed 8313:31715, Loading 8313:31968",
    inSitemap: false,
  },
  {
    path: "/messages/new",
    file: "app/messages/new/page.tsx",
    title: "New message",
    group: "Account",
    access: "signed-in",
    purpose: "Write to the Bluntly team: a topic, optionally linked to one of your payouts, reviews or reports, a message and a screenshot.",
    figma: "Screen/Messages/New 8296:31389, New/Error 8313:31919, Sheet/Messages/Link 8313:32096, Sheet/Messages/Attach 8313:32017",
    inSitemap: false,
  },
  {
    path: "/messages/[id]",
    file: "app/messages/[id]/page.tsx",
    title: "Conversation",
    group: "Account",
    access: "signed-in",
    purpose: "One of your conversations with the team: replies (a reply reopens a closed one), Email me a copy, Mark as resolved.",
    figma: "Screen/Messages/Thread 8296:31305, Sent 8296:31467, Thread/Sending 8313:31785, Thread/Failed 8313:31818, Thread/Closed 8313:31853, Sheet/Messages/More 8313:32059, Confirm/Messages/Resolve 8313:32146, Toast/Messages/Copy sent 8313:32156",
    inSitemap: false,
  },
  {
    path: "/sellers/[id]/support/new",
    file: "app/sellers/[id]/support/new/page.tsx",
    title: "New support request (retired)",
    group: "Account",
    access: "store-owner",
    purpose: "Retired 2026-10-03: redirects to New message in the Seller console (/seller/[storeId]/messages?new=1). Requests filed before keep their own pages.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/sellers/[id]/support/[requestId]",
    file: "app/sellers/[id]/support/[requestId]/page.tsx",
    title: "Support request",
    group: "Account",
    access: "store-owner",
    purpose: "One support request as its store's owner sees it: their message, its status and the administrator's reply.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/sellers/[id]/reports",
    file: "app/sellers/[id]/reports/page.tsx",
    title: "Rating summary",
    group: "Account",
    access: "store-owner",
    purpose: "Report 3: a store's rating summary for a period (its approved owner, or staff), with CSV and print.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/sellers/appeals/[id]",
    file: "app/sellers/appeals/[id]/page.tsx",
    title: "Back up a store review",
    group: "Account",
    access: "signed-in",
    purpose: "Where a reviewer answers an admin's request to substantiate a store review a seller disputed.",
    figma: null,
    inSitemap: false,
  },

  // ------------------------------------------------------------------ Earnings
  {
    path: "/dashboard",
    file: "app/dashboard/page.tsx",
    title: "Dashboard",
    group: "Earnings",
    access: "signed-in",
    purpose: "The contributor dashboard: Payout / History / Performance, the wallet (commission, Honesty Fund, pending), earned vs returned, best performing, trust stage and what the next asks, Honesty Score, reach.",
    figma: "Screen/Dashboard (7833:9534)",
    inSitemap: false,
  },
  {
    path: "/dashboard/history",
    file: "app/dashboard/history/page.tsx",
    title: "Earnings history",
    group: "Earnings",
    access: "signed-in",
    purpose: "All-time income and every commission behind it.",
    figma: "Reviewer Dashboard - History (5762:472, 6158:1240)",
    inSitemap: false,
  },
  {
    path: "/dashboard/statement",
    file: "app/dashboard/statement/page.tsx",
    title: "Earnings statement",
    group: "Earnings",
    access: "signed-in",
    purpose: "Report 4: your own earnings per review, cleared vs clearing, cashouts and payouts, with CSV and print.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/dashboard/reviews",
    file: "app/dashboard/reviews/page.tsx",
    title: "Your reviews",
    group: "Earnings",
    access: "signed-in",
    purpose: "Your reviews and how each is doing.",
    figma: "Reviewer Dashboard - Reviews (6159:1510)",
    inSitemap: false,
  },
  {
    path: "/dashboard/transfer",
    file: "app/dashboard/transfer/page.tsx",
    title: "Payout",
    group: "Earnings",
    access: "signed-in",
    purpose: "Cleared money as a commission / Honesty Fund ring, minimum met or how much to go, how payouts work, where they go, your requests and the request button.",
    figma: "Screen/Payout (7840:9380), Screen/Payout/Locked (7840:9462)",
    inSitemap: false,
  },
  {
    path: "/dashboard/transfer/details",
    file: "app/dashboard/transfer/details/page.tsx",
    title: "Payout details",
    group: "Earnings",
    access: "signed-in",
    purpose: "Where payouts are sent (PayPal) and the name on that account.",
    figma: "Screen/Payout/Details (7843:9432)",
    inSitemap: false,
  },
  {
    path: "/dashboard/transfer/answers",
    file: "app/dashboard/transfer/answers/page.tsx",
    title: "Answer open questions",
    group: "Earnings",
    access: "signed-in",
    purpose: "Payout tip: answers this month, what answers earned, and unanswered questions in the member's category.",
    figma: "Payout tip (7844:9469)",
    inSitemap: false,
  },
  {
    path: "/dashboard/transfer/honest-reviews",
    file: "app/dashboard/transfer/honest-reviews/page.tsx",
    title: "Honest low-star reviews pay too",
    group: "Earnings",
    access: "signed-in",
    purpose: "Payout tip: 3★ and up earn commission, 2★ and below the Honesty Fund; the member's Honesty Score.",
    figma: "Payout tip (7844:9529)",
    inSitemap: false,
  },
  {
    path: "/dashboard/transfer/proof",
    file: "app/dashboard/transfer/proof/page.tsx",
    title: "Add receipts and photos",
    group: "Earnings",
    access: "signed-in",
    purpose: "Payout tip: average earning per review with and without proof, and the member's reviews missing proof.",
    figma: "Payout tip (7843:9501)",
    inSitemap: false,
  },
  {
    path: "/dashboard/insights",
    file: "app/dashboard/insights/page.tsx",
    title: "Performance",
    group: "Earnings",
    access: "signed-in",
    purpose: "How your reviews perform, all or one product: rating, earned / views / helped, 30-day earnings, votes, view-to-buy, the commission split, marketplaces, reviews by earnings.",
    figma: "Screen/Performance (7848:9542)",
    inSitemap: false,
  },

  // ------------------------------------------------------------------- Company
  {
    path: "/about",
    file: "app/about/page.tsx",
    title: "About",
    group: "Company",
    access: "public",
    purpose: "What bluntly is: reviews by real buyers, checked by administrators, never paid for by brands.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/how-it-works",
    file: "app/how-it-works/page.tsx",
    title: "How it works",
    group: "Company",
    access: "public",
    purpose: "How a real purchase becomes a moderated review that pays the person who wrote it.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/membership",
    file: "app/membership/page.tsx",
    title: "Membership tiers",
    group: "Company",
    access: "public",
    purpose: "Special, Founding and Standard tiers: revenue share and payout priority. Tiers are earned, never bought.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/faqs",
    file: "app/faqs/page.tsx",
    title: "FAQs",
    group: "Company",
    access: "public",
    purpose: "Common questions: earning, verification, payouts and getting started.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/articles",
    file: "app/articles/page.tsx",
    title: "Articles",
    group: "Company",
    access: "public",
    purpose: "Guides and explainers from the bluntly team (coming soon).",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/contact",
    file: "app/contact/page.tsx",
    title: "Contact",
    group: "Company",
    access: "public",
    purpose: "Reach the team about support, moderation, press, partnerships or feedback.",
    figma: null,
    inSitemap: true,
  },

  // --------------------------------------------------------------------- Legal
  {
    path: "/guidelines",
    file: "app/guidelines/page.tsx",
    title: "Community guidelines",
    group: "Legal",
    access: "public",
    purpose: "The rules that keep reviews real: genuine experience, independence, original words and photos.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/legal",
    file: "app/legal/page.tsx",
    title: "Legal & disclosures",
    group: "Legal",
    access: "public",
    purpose: "How bluntly makes money, the affiliate disclosure, and links to the policies.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/terms",
    file: "app/terms/page.tsx",
    title: "Terms & Conditions",
    group: "Legal",
    access: "public",
    purpose: "The terms for accounts, content, acceptable use, affiliate earnings and payouts.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/privacy",
    file: "app/privacy/page.tsx",
    title: "Privacy Policy",
    group: "Legal",
    access: "public",
    purpose: "What bluntly.ph collects, why, and the choices you have.",
    figma: null,
    inSitemap: true,
  },
  {
    path: "/unsubscribe",
    file: "app/unsubscribe/page.tsx",
    title: "Unsubscribe",
    group: "Account",
    access: "public",
    purpose: "The footer link of every store email: turns that email off from a signed link, no sign-in.",
    figma: null,
    inSitemap: false,
  },

  // ------------------------------------------------------------ Administration
  {
    path: "/admin",
    file: "app/admin/page.tsx",
    title: "Overview",
    group: "Administration",
    access: "administrator",
    purpose: "The administrator landing: what is urgent, summary figures and recent activity.",
    // The Overview frame (5017:1738) is no longer in the file; the shell is.
    figma: "Admin/Sidebar shell (5017:2225)",
    inSitemap: false,
  },
  {
    path: "/admin/review-queue",
    file: "app/admin/review-queue/page.tsx",
    title: "Review queue",
    group: "Administration",
    access: "administrator",
    purpose: "Reviews waiting for a administrator, with the Q&A and Support tabs; filtered and paged on the server.",
    figma: "Admin Page - Review Queue (6922:837), the file's one desktop frame",
    inSitemap: false,
  },
  {
    path: "/admin/products",
    file: "app/admin/products/page.tsx",
    title: "Products",
    group: "Administration",
    access: "administrator",
    purpose: "The product catalogue, read-only, with how much has been written about each.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/prices",
    file: "app/admin/prices/page.tsx",
    title: "Prices",
    group: "Administration",
    access: "administrator",
    purpose: "Community price reports waiting for approval before they reach a product page.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/sellers",
    file: "app/admin/sellers/page.tsx",
    title: "Sellers",
    group: "Administration",
    access: "administrator",
    purpose: "Seller claims waiting for a administrator, with the claimant's evidence beside the store.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/reviewers",
    file: "app/admin/reviewers/page.tsx",
    title: "People",
    group: "Administration",
    access: "administrator",
    purpose: "Members by standing (active, under investigation, suspended); each opens their investigation.",
    figma: "7998:11693",
    inSitemap: false,
  },
  {
    path: "/admin/people",
    file: "app/admin/people/page.tsx",
    title: "People (redirect)",
    group: "Administration",
    access: "administrator",
    purpose: "Parent of one person's page; redirects to the People list (/admin/reviewers) instead of a 404.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/people/[id]",
    file: "app/admin/people/[id]/page.tsx",
    title: "Person investigation",
    group: "Administration",
    access: "administrator",
    purpose: "One member: votes, interactions and reciprocity, activity, reports, moderation, earnings, linked accounts.",
    figma: "8005:11974",
    inSitemap: false,
  },
  {
    path: "/admin/users",
    file: "app/admin/users/page.tsx",
    title: "User management",
    group: "Administration",
    access: "super-admin",
    purpose: "Super Admin: find an account and move it between Member, Administrator and Super Admin, never leaving the platform without a Super Admin.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/inbox",
    file: "app/admin/inbox/page.tsx",
    title: "Inbox",
    group: "Administration",
    access: "administrator",
    purpose: "Conversations with sellers and reviewers: reply (also emailed), assign, mark waiting or closed, reopen, move a store's conversation to Queue → Support. A claim's or an appeal's chat is the same thread.",
    figma: "Screen/Admin/Inbox (8291:30461), Reviewers (8293:31035), Closed (8293:31377), Empty (8314:32508), Loading (8314:31910), Menu/Inbox/* (8294:*), Confirm/Inbox/Close (8294:31318)",
    inSitemap: false,
  },
  {
    path: "/admin/special-routing",
    file: "app/admin/special-routing/page.tsx",
    title: "Special routing",
    group: "Administration",
    access: "super-admin",
    purpose: "Super Admin: route each 2.5-star \"It depends\" review an Administrator approved to the Honesty Fund or the platform, with the audited history.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/affiliate-links",
    file: "app/admin/affiliate-links/page.tsx",
    title: "Affiliate",
    group: "Administration",
    access: "administrator",
    purpose: "The affiliate ledger: what the marketplace reported and what our own ledger settled.",
    figma: "Screen/Admin/Affiliate (8015:12542), Months (8015:13183), Imports (8015:13726), Import (8017:12742), Remittance (8017:12816)",
    inSitemap: false,
  },
  {
    path: "/admin/honesty-fund",
    file: "app/admin/honesty-fund/page.tsx",
    title: "Honesty Fund",
    group: "Administration",
    access: "administrator",
    purpose: "The Honesty Fund pool for the current cycle. Distribution is scheduled, not a button.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/payouts",
    file: "app/admin/payouts/page.tsx",
    title: "Payouts",
    group: "Administration",
    access: "administrator",
    purpose: "Reviewers' withdrawal requests: send to PayPal sandbox, or mark paid, failed or cancelled.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/reports",
    file: "app/admin/reports/page.tsx",
    title: "Reports",
    group: "Administration",
    access: "administrator",
    purpose: "The month's money (net commission and its split, money in, money out, still owed) and the branded PDF reports generated so far; Generate report builds one for a month, quarter, year or dates.",
    figma: "Screen/Admin/Reports (8028:12886), Overlay/Report/Generate (8028:13346), PDF/Financial report (8029:12942, 8029:13078)",
    inSitemap: false,
  },
  {
    path: "/admin/reports/honesty-fund",
    file: "app/admin/reports/honesty-fund/page.tsx",
    title: "Honesty Fund report",
    group: "Administration",
    access: "administrator",
    purpose: "Report 1: fund inflow and every fund-track review's inputs; the distribution waits on its formula.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/reports/commissions",
    file: "app/admin/reports/commissions/page.tsx",
    title: "Commissions & payouts report",
    group: "Administration",
    access: "administrator",
    purpose: "Report 2: imported commissions, their split and reconciliation, and every reviewer against the ₱300 minimum.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/reports/seller-ratings",
    file: "app/admin/reports/seller-ratings/page.tsx",
    title: "Seller ratings",
    group: "Administration",
    access: "administrator",
    purpose: "Pick a store to open its rating summary (Report 3).",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/qa-sandbox",
    file: "app/admin/qa-sandbox/page.tsx",
    title: "QA Payments",
    group: "Administration",
    access: "administrator",
    purpose: "Owner-named QA testers and their sandbox test earnings, for testing payouts end to end.",
    figma: null,
    inSitemap: false,
  },
  {
    path: "/admin/analytics",
    file: "app/admin/analytics/page.tsx",
    title: "Analytics",
    group: "Administration",
    access: "administrator",
    purpose: "Key figures against the period before, reviews per day, the review-to-commission funnel, moderation, community, top products, reader cities and integrity findings.",
    figma: "Screen/Admin/Analytics (8071:16115)",
    inSitemap: false,
  },
  {
    path: "/admin/activity",
    file: "app/admin/activity/page.tsx",
    title: "Activity log",
    group: "Administration",
    access: "administrator",
    purpose: "The full moderation audit log.",
    figma: "Screen/Admin/ActivityLog (8074:16245)",
    inSitemap: false,
  },
  {
    path: "/admin/settings",
    file: "app/admin/settings/page.tsx",
    title: "Settings",
    group: "Administration",
    access: "administrator",
    purpose: "Team, earning and payout rules, integrations and data retention, as the services run them (read-only).",
    figma: "Screen/Admin/Settings (8076:16388)",
    inSitemap: false,
  },
];

export type SystemRoute = {
  path: string;
  /** "app": a route handler in this repo's app/; "backend": rewritten to the API service (vercel.json). */
  source: "app" | "backend" | "metadata";
  purpose: string;
};

/** Addresses that are not pages. Listed so the inventory has no unknown routes. */
export const SYSTEM_ROUTES: SystemRoute[] = [
  { path: "/api/bff/[...path]", source: "app", purpose: "The browser's proxy to the API, carrying the session cookie." },
  { path: "/api/telemetry", source: "app", purpose: "Reading telemetry from review pages." },
  { path: "/api/v1/*", source: "backend", purpose: "The FastAPI service." },
  { path: "/r/*", source: "backend", purpose: "Attributed affiliate redirects to the marketplace." },
  { path: "/health", source: "backend", purpose: "The API's health check." },
  { path: "/sitemap.xml", source: "metadata", purpose: "This map's public pages, for search engines (app/sitemap.ts)." },
  { path: "/robots.txt", source: "metadata", purpose: "Crawler rules and the sitemap's address (app/robots.ts)." },
  { path: "/icon.svg", source: "metadata", purpose: "The site icon (app/icon.svg)." },
];

/** The paths /sitemap.xml lists. */
export function sitemapPaths(): string[] {
  return SITE_ROUTES.filter((r) => r.inSitemap).map((r) => r.path);
}

const ACCESS_LABEL: Record<Access, string> = {
  public: "Public",
  "signed-out": "Signed-out only",
  "signed-in": "Signed in",
  administrator: "Administrator",
  "super-admin": "Super Admin",
  "store-owner": "Store owner",
};

const GROUPS: Group[] = [
  "Discover",
  "Community",
  "Write",
  "Sign in",
  "Account",
  "Earnings",
  "Company",
  "Legal",
  "Administration",
];

const cell = (text: string) => text.replace(/\|/g, "\\|");

/** docs/SITEMAP.md, generated from this file by `npm run sitemap:docs`. */
export function siteMapMarkdown(): string {
  const withFigma = SITE_ROUTES.filter((r) => r.figma !== null).length;
  const lines: string[] = [
    "# bluntly.ph site map",
    "",
    "<!-- Generated from lib/site-map.ts by `npm run sitemap:docs`. Edit that file, not this one. -->",
    "",
    `${SITE_ROUTES.length} pages: ${withFigma} built to Figma frames, ${SITE_ROUTES.length - withFigma} with no frame in the file`,
    "(product and business pages kept from the PRD, styled in the Figma system's language).",
    `${sitemapPaths().length} public pages are listed in ${SITE_URL}/sitemap.xml.`,
    "",
    "Access: **Public** anyone; **Signed-out only** a signed-in reader is sent home; **Signed in** a",
    "signed-out visitor is sent to /login and brought back; **Administrator** signed in as an Administrator",
    "or a Super Admin; **Super Admin** signed in as a Super Admin (an Administrator is told the section is",
    "not theirs, and the API refuses them); **Store owner** signed in, and only the store's approved owner",
    "sees its figures.",
    "",
  ];
  for (const group of GROUPS) {
    const routes = SITE_ROUTES.filter((r) => r.group === group);
    if (routes.length === 0) continue;
    lines.push(`## ${group}`, "", "| Page | Path | Access | What it is for | Figma | sitemap.xml |", "| --- | --- | --- | --- | --- | --- |");
    for (const r of routes) {
      lines.push(
        `| ${cell(r.title)} | \`${r.path}\` | ${ACCESS_LABEL[r.access]} | ${cell(r.purpose)} | ${
          r.figma ? cell(r.figma) : "No frame"
        } | ${r.inSitemap ? "Yes" : "No"} |`,
      );
    }
    lines.push("");
  }
  lines.push("## Not pages", "", "| Path | Served by | What it is for |", "| --- | --- | --- |");
  for (const r of SYSTEM_ROUTES) {
    const by = r.source === "app" ? "Next route handler" : r.source === "backend" ? "API service" : "Next metadata";
    lines.push(`| \`${r.path}\` | ${by} | ${cell(r.purpose)} |`);
  }
  lines.push("");
  return lines.join("\n");
}
