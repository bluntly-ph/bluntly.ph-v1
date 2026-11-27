# bluntly.ph site map

<!-- Generated from lib/site-map.ts by `npm run sitemap:docs`. Edit that file, not this one. -->

88 pages: 50 built to Figma frames, 38 with no frame in the file
(product and business pages kept from the PRD, styled in the Figma system's language).
15 public pages are listed in https://www.bluntly.ph/sitemap.xml.

Access: **Public** anyone; **Signed-out only** a signed-in reader is sent home; **Signed in** a
signed-out visitor is sent to /login and brought back; **Administrator** signed in as an Administrator
or a Super Admin; **Super Admin** signed in as a Super Admin (an Administrator is told the section is
not theirs, and the API refuses them); **Store owner** signed in, and only the store's approved owner
sees its figures.

## Discover

| Page | Path | Access | What it is for | Figma | sitemap.xml |
| --- | --- | --- | --- | --- | --- |
| Landing | `/` | Public | The front door: what bluntly is, the ask-anything search, a featured review and the trust story. | Mobile Landing Page (1902:1504) | Yes |
| Search | `/search` | Public | Search reviews, questions and sellers in tabs, with filters, sort and recent searches. Has the + action button. | Mobile Search Page for Buyers / Reviewers / Sellers (3481:1776, 3481:1894, 3954:650), All filters, Sort | No |
| Categories | `/categories` | Public | Browse every product category; a category opens search filtered to it. | Categories (2355:939), Subcategory (2355:2267) | Yes |
| Feed | `/feed` | Public | The browsing surface for readers who already know bluntly: the latest honest reviews. | No frame | Yes |
| Compare products | `/compare` | Public | Side-by-side product comparison, chosen by id in the link (?ids=a,b,c) so it can be shared. | No frame | No |
| Review | `/reviews/[id]` | Public | One review in full: verdict, rating, pros and cons, photos, votes, comments, prices and where to buy. | Review page (4218:1196), More actions, Share to, Shop, Read more | No |
| Seller | `/sellers/[id]` | Public | A store's page: rating summary, seller reviews and questions. Has the + action button. | Seller Page - Review (4218:2148), Seller Page - Questions (4295:1256), Action Menu (4417:751) | No |
| Public profile | `/u/[id]` | Public | A reviewer's public profile: their stats and published reviews. | Profile Page - Reviews / Comments / Stats (5446:4328, 5446:6398, 5446:6532) | No |

## Community

| Page | Path | Access | What it is for | Figma | sitemap.xml |
| --- | --- | --- | --- | --- | --- |
| Questions | `/questions` | Public | Every open question from the community, newest first, with a way to ask one. | No frame | Yes |
| Question | `/questions/[id]` | Public | One question with its answers; answer it, or mark the best answer if it is yours. | No frame | No |
| Answer a question | `/questions/[id]/answer` | Signed in | The seven-step answer: your words, experience, pros and cons, verdict, fit, rating and a photo. | Answer Page - Step 1..7, All done (7573:8215 to 7573:9158) | No |
| Requests | `/requests` | Public | The request board ("Bounty board" in the menu): products people have asked to see reviewed. | No frame | Yes |
| Request | `/requests/[id]` | Public | One review request, for good: its product, every review that answers it, and the asker's Best Answer (picked here). | No frame | No |

## Write

| Page | Path | Access | What it is for | Figma | sitemap.xml |
| --- | --- | --- | --- | --- | --- |
| Write a review | `/reviews/new` | Signed in | The seven-step product review composer, with proof of purchase, the price check and the done screen. | Reviewer Page - Step 1 to Step 7.1, All done (4550:8882), Let's talk money | No |
| Rate a seller | `/sellers/rate` | Signed in | Find or add a store, rate it on four dimensions, write it up; seller reviews go live on posting. | Seller Review - Step 1 to Step 3.3, All done (4652:12914) | No |
| Ask a question | `/questions/new` | Signed in | Choose who answers (buyers or the seller), pick the product, write the question. | Question Page - Buyer or Seller (4682:14203), Step 1 to Step 3 (4742:15979) | No |
| Post a request | `/requests/new` | Signed in | Ask for a product to be reviewed. | No frame | No |

## Sign in

| Page | Path | Access | What it is for | Figma | sitemap.xml |
| --- | --- | --- | --- | --- | --- |
| Welcome | `/welcome` | Signed-out only | The entry screen: continue to sign up or log in. | Login & Signup (5357:2982) | No |
| Log in | `/login` | Signed-out only | Email one-time-code login; returns the reader to the page that sent them (?next=). | Login & Signup (5348:2789 family) | No |
| Sign up | `/signup` | Signed-out only | Create an account with an emailed one-time code. | Login & Signup (5348:2789 family) | No |
| Set up your profile | `/onboarding` | Signed in | First-run setup: username, profile and interests. | Login & Signup onboarding states, InterestTile (6842:567), StepBar (6820:477) | No |

## Account

| Page | Path | Access | What it is for | Figma | sitemap.xml |
| --- | --- | --- | --- | --- | --- |
| Edit your profile | `/profile/edit` | Signed in | Change your handle, display name, photo and interests in one form. | No frame — BUSINESS-REQUIRED (BUG-035). The file draws onboarding, which is a different job. | No |
| Your profile | `/profile` | Signed in | Your own profile: stats, verified reviews, comments, and sharing it. | Profile Page - Reviews / Comments / Stats (5446:4328, 5446:6398, 5446:6532) | No |
| Notifications | `/notifications` | Signed in | Your account's notifications. | No frame | No |
| Store dashboard | `/sellers/[id]/dashboard` | Store owner | Old address of the store dashboard; redirects to the Seller console (/seller/[storeId]). | No frame | No |
| Seller dashboard | `/seller/dashboard` | Signed in | The claimed seller's way in: opens the Seller console on their first store, or says how to claim one and where a claim in review stands. | No frame | No |
| Seller console — Overview | `/seller/[storeId]` | Store owner | The approved owner's Overview: rating tiles for a period, what is waiting on them, rating breakdown, reviews per month, reply rates and recent reviews; store switcher and claim status in the rail. | Screen/Seller/Overview 8190:20643 | No |
| Seller console — Reviews | `/seller/[storeId]/reviews` | Store owner | The store's reviews by Needs response / Responded / All, with sort, filters and search; respond, edit the response, or flag a review as suspected fake. | Screen/Seller/Reviews 8196:20870 | No |
| Seller console — Appeals | `/seller/[storeId]/appeals` | Store owner | The flags the store raised against reviews it believes are fake, In progress / Decided, with where each stands. | Screen/Seller/Appeals 8196:21910 | No |
| Seller console — Questions | `/seller/[storeId]/questions` | Store owner | Questions about the store, Unanswered / Answered / All, with answer rate and time to answer; answer as the store. | Screen/Seller/Questions 8196:21469 | No |
| Seller console — Settings | `/seller/[storeId]/settings` | Store owner | The owner's account (profile: display name and username), what notifications reach them, and Contact support. | Screen/Seller/Settings 8218:24151 | No |
| Seller console — Seller rules | `/seller/[storeId]/rules` | Store owner | What a claim gives a store owner and what it never does: responses, flags, how the store rating is worked out, owning a store. | Screen/Seller/SellerRules 8218:23740 | No |
| Products (Seller console) | `/seller/[storeId]/products` | Store owner | The product pages the store links to: Linked, Waiting for approval, All; Link a product (a moderator approves), cancel a request, ask for a missing product page; per-product figures. | Screen/Seller/Products 8204:22648, Waiting 8214:23301, All 8214:23647, Loading 8228:26685, Overlay/Store/LinkProduct 8204:23173, Confirm/Store/LinkProduct 8213:23439, Confirm/Store/CancelLink 8213:23484, Overlay/Store/RequestProduct 8213:23372 (+Similar 8278:29593), Menu/Seller/Products/* 8213:* | No |
| Product analytics (Seller console) | `/seller/[storeId]/products/[productId]` | Store owner | A linked product's figures for its store: median and 30-day change, verdicts, the 6-month trend against its category, recurring pros and cons, category comparisons, recent questions. | Screen/Seller/Products/Analytics 8205:22802 | No |
| Insights (Seller console) | `/seller/[storeId]/insights` | Store owner | The store's own reviews over a period: rating, review count against the period before, would recommend, response rate, order facts by month, replies by month and median time to reply, the median store on the same marketplace; Download CSV. | Screen/Seller/Insights 8208:22905, Loading 8228:27172, Overlay/Store/Export 8213:23286, Menu/Store/Period 8212:23210 | No |
| Store profile (Seller console) | `/seller/[storeId]/profile` | Store owner | The store as buyers see it, how its claim was verified (registration shown by its last 4 characters only), what owning a store allows, the account's stores; Request a change (sent to the team as a message) and Give up the store. | Screen/Seller/StoreProfile 8209:23011, Loading 8228:27673, Overlay/Store/RequestChange 8209:23626, Confirm/Store/GiveUp 8220:24024 | No |
| Public page (Seller console) | `/seller/[storeId]/public` | Store owner | The store's public page read inside the console: its figures, reviews (Most helpful, Newest, Lowest rating) with the store's responses, the ratings breakdown and store questions; Open on Bluntly. | Screen/Seller/PublicPage 8217:23574, Loading 8228:28024 | No |
| Messages (Seller console) | `/seller/[storeId]/messages` | Store owner | The store owner and the Bluntly team: open and closed conversations, New message about an appeal, a claim, a product page or the store, replies (a reply reopens a closed one), attachments. | Screen/Seller/Inbox 8304:32524, Closed 8305:31810, Empty 8314:32768, Loading 8314:32250, Overlay/Store/Chat/New 8276:29363 (+Error 8314:33626), Menu/Store/Chat/Topic 8276:29564, Menu/Store/Chat/Appeal 8287:29845 | No |
| Messages | `/messages` | Signed in | You and the Bluntly team: open and closed conversations about a payout, a review you wrote, a report you made or your account. | Screen/Messages 8296:31219, Empty 8296:31548, Closed 8313:31715, Loading 8313:31968 | No |
| New message | `/messages/new` | Signed in | Write to the Bluntly team: a topic, optionally linked to one of your payouts, reviews or reports, a message and a screenshot. | Screen/Messages/New 8296:31389, New/Error 8313:31919, Sheet/Messages/Link 8313:32096, Sheet/Messages/Attach 8313:32017 | No |
| Conversation | `/messages/[id]` | Signed in | One of your conversations with the team: replies (a reply reopens a closed one), Email me a copy, Mark as resolved. | Screen/Messages/Thread 8296:31305, Sent 8296:31467, Thread/Sending 8313:31785, Thread/Failed 8313:31818, Thread/Closed 8313:31853, Sheet/Messages/More 8313:32059, Confirm/Messages/Resolve 8313:32146, Toast/Messages/Copy sent 8313:32156 | No |
| New support request (retired) | `/sellers/[id]/support/new` | Store owner | Retired 2026-10-03: redirects to New message in the Seller console (/seller/[storeId]/messages?new=1). Requests filed before keep their own pages. | No frame | No |
| Support request | `/sellers/[id]/support/[requestId]` | Store owner | One support request as its store's owner sees it: their message, its status and the administrator's reply. | No frame | No |
| Rating summary | `/sellers/[id]/reports` | Store owner | Report 3: a store's rating summary for a period (its approved owner, or staff), with CSV and print. | No frame | No |
| Back up a store review | `/sellers/appeals/[id]` | Signed in | Where a reviewer answers an admin's request to substantiate a store review a seller disputed. | No frame | No |
| Unsubscribe | `/unsubscribe` | Public | The footer link of every store email: turns that email off from a signed link, no sign-in. | No frame | No |

## Earnings

| Page | Path | Access | What it is for | Figma | sitemap.xml |
| --- | --- | --- | --- | --- | --- |
| Dashboard | `/dashboard` | Signed in | The contributor dashboard: Payout / History / Performance, the wallet (commission, Honesty Fund, pending), earned vs returned, best performing, trust stage and what the next asks, Honesty Score, reach. | Screen/Dashboard (7833:9534) | No |
| Earnings history | `/dashboard/history` | Signed in | All-time income and every commission behind it. | Reviewer Dashboard - History (5762:472, 6158:1240) | No |
| Earnings statement | `/dashboard/statement` | Signed in | Report 4: your own earnings per review, cleared vs clearing, cashouts and payouts, with CSV and print. | No frame | No |
| Your reviews | `/dashboard/reviews` | Signed in | Your reviews and how each is doing. | Reviewer Dashboard - Reviews (6159:1510) | No |
| Payout | `/dashboard/transfer` | Signed in | Cleared money as a commission / Honesty Fund ring, minimum met or how much to go, how payouts work, where they go, your requests and the request button. | Screen/Payout (7840:9380), Screen/Payout/Locked (7840:9462) | No |
| Payout details | `/dashboard/transfer/details` | Signed in | Where payouts are sent (PayPal) and the name on that account. | Screen/Payout/Details (7843:9432) | No |
| Answer open questions | `/dashboard/transfer/answers` | Signed in | Payout tip: answers this month, what answers earned, and unanswered questions in the member's category. | Payout tip (7844:9469) | No |
| Honest low-star reviews pay too | `/dashboard/transfer/honest-reviews` | Signed in | Payout tip: 3★ and up earn commission, 2★ and below the Honesty Fund; the member's Honesty Score. | Payout tip (7844:9529) | No |
| Add receipts and photos | `/dashboard/transfer/proof` | Signed in | Payout tip: average earning per review with and without proof, and the member's reviews missing proof. | Payout tip (7843:9501) | No |
| Performance | `/dashboard/insights` | Signed in | How your reviews perform, all or one product: rating, earned / views / helped, 30-day earnings, votes, view-to-buy, the commission split, marketplaces, reviews by earnings. | Screen/Performance (7848:9542) | No |

## Company

| Page | Path | Access | What it is for | Figma | sitemap.xml |
| --- | --- | --- | --- | --- | --- |
| About | `/about` | Public | What bluntly is: reviews by real buyers, checked by administrators, never paid for by brands. | No frame | Yes |
| How it works | `/how-it-works` | Public | How a real purchase becomes a moderated review that pays the person who wrote it. | No frame | Yes |
| Membership tiers | `/membership` | Public | Special, Founding and Standard tiers: revenue share and payout priority. Tiers are earned, never bought. | No frame | Yes |
| FAQs | `/faqs` | Public | Common questions: earning, verification, payouts and getting started. | No frame | Yes |
| Articles | `/articles` | Public | Guides and explainers from the bluntly team (coming soon). | No frame | Yes |
| Contact | `/contact` | Public | Reach the team about support, moderation, press, partnerships or feedback. | No frame | Yes |

## Legal

| Page | Path | Access | What it is for | Figma | sitemap.xml |
| --- | --- | --- | --- | --- | --- |
| Community guidelines | `/guidelines` | Public | The rules that keep reviews real: genuine experience, independence, original words and photos. | No frame | Yes |
| Legal & disclosures | `/legal` | Public | How bluntly makes money, the affiliate disclosure, and links to the policies. | No frame | Yes |
| Terms & Conditions | `/terms` | Public | The terms for accounts, content, acceptable use, affiliate earnings and payouts. | No frame | Yes |
| Privacy Policy | `/privacy` | Public | What bluntly.ph collects, why, and the choices you have. | No frame | Yes |

## Administration

| Page | Path | Access | What it is for | Figma | sitemap.xml |
| --- | --- | --- | --- | --- | --- |
| Overview | `/admin` | Administrator | The administrator landing: what is urgent, summary figures and recent activity. | Admin/Sidebar shell (5017:2225) | No |
| Review queue | `/admin/review-queue` | Administrator | Reviews waiting for a administrator, with the Q&A and Support tabs; filtered and paged on the server. | Admin Page - Review Queue (6922:837), the file's one desktop frame | No |
| Products | `/admin/products` | Administrator | The product catalogue, read-only, with how much has been written about each. | No frame | No |
| Prices | `/admin/prices` | Administrator | Community price reports waiting for approval before they reach a product page. | No frame | No |
| Sellers | `/admin/sellers` | Administrator | Seller claims waiting for a administrator, with the claimant's evidence beside the store. | No frame | No |
| People | `/admin/reviewers` | Administrator | Members by standing (active, under investigation, suspended); each opens their investigation. | 7998:11693 | No |
| People (redirect) | `/admin/people` | Administrator | Parent of one person's page; redirects to the People list (/admin/reviewers) instead of a 404. | No frame | No |
| Person investigation | `/admin/people/[id]` | Administrator | One member: votes, interactions and reciprocity, activity, reports, moderation, earnings, linked accounts. | 8005:11974 | No |
| User management | `/admin/users` | Super Admin | Super Admin: find an account and move it between Member, Administrator and Super Admin, never leaving the platform without a Super Admin. | No frame | No |
| Inbox | `/admin/inbox` | Administrator | Conversations with sellers and reviewers: reply (also emailed), assign, mark waiting or closed, reopen, move a store's conversation to Queue → Support. A claim's or an appeal's chat is the same thread. | Screen/Admin/Inbox (8291:30461), Reviewers (8293:31035), Closed (8293:31377), Empty (8314:32508), Loading (8314:31910), Menu/Inbox/* (8294:*), Confirm/Inbox/Close (8294:31318) | No |
| Special routing | `/admin/special-routing` | Super Admin | Super Admin: route each 2.5-star "It depends" review an Administrator approved to the Honesty Fund or the platform, with the audited history. | No frame | No |
| Affiliate | `/admin/affiliate-links` | Administrator | The affiliate ledger: what the marketplace reported and what our own ledger settled. | Screen/Admin/Affiliate (8015:12542), Months (8015:13183), Imports (8015:13726), Import (8017:12742), Remittance (8017:12816) | No |
| Honesty Fund | `/admin/honesty-fund` | Administrator | The Honesty Fund pool for the current cycle. Distribution is scheduled, not a button. | No frame | No |
| Payouts | `/admin/payouts` | Administrator | Reviewers' withdrawal requests: send to PayPal sandbox, or mark paid, failed or cancelled. | No frame | No |
| Reports | `/admin/reports` | Administrator | The month's money (net commission and its split, money in, money out, still owed) and the branded PDF reports generated so far; Generate report builds one for a month, quarter, year or dates. | Screen/Admin/Reports (8028:12886), Overlay/Report/Generate (8028:13346), PDF/Financial report (8029:12942, 8029:13078) | No |
| Honesty Fund report | `/admin/reports/honesty-fund` | Administrator | Report 1: fund inflow and every fund-track review's inputs; the distribution waits on its formula. | No frame | No |
| Commissions & payouts report | `/admin/reports/commissions` | Administrator | Report 2: imported commissions, their split and reconciliation, and every reviewer against the ₱300 minimum. | No frame | No |
| Seller ratings | `/admin/reports/seller-ratings` | Administrator | Pick a store to open its rating summary (Report 3). | No frame | No |
| QA Payments | `/admin/qa-sandbox` | Administrator | Owner-named QA testers and their sandbox test earnings, for testing payouts end to end. | No frame | No |
| Analytics | `/admin/analytics` | Administrator | Key figures against the period before, reviews per day, the review-to-commission funnel, moderation, community, top products, reader cities and integrity findings. | Screen/Admin/Analytics (8071:16115) | No |
| Activity log | `/admin/activity` | Administrator | The full moderation audit log. | Screen/Admin/ActivityLog (8074:16245) | No |
| Settings | `/admin/settings` | Administrator | Team, earning and payout rules, integrations and data retention, as the services run them (read-only). | Screen/Admin/Settings (8076:16388) | No |

## Not pages

| Path | Served by | What it is for |
| --- | --- | --- |
| `/api/bff/[...path]` | Next route handler | The browser's proxy to the API, carrying the session cookie. |
| `/api/telemetry` | Next route handler | Reading telemetry from review pages. |
| `/api/v1/*` | API service | The FastAPI service. |
| `/r/*` | API service | Attributed affiliate redirects to the marketplace. |
| `/health` | API service | The API's health check. |
| `/sitemap.xml` | Next metadata | This map's public pages, for search engines (app/sitemap.ts). |
| `/robots.txt` | Next metadata | Crawler rules and the sitemap's address (app/robots.ts). |
| `/icon.svg` | Next metadata | The site icon (app/icon.svg). |
