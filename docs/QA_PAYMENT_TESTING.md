# Testing payouts with real QA testers (PayPal sandbox)

Owner decision, 2026-09-27: real QA testers must be able to test **getting paid**
on www.bluntly.ph before the defense. None of them will have made a marketplace
sale through a Bluntly link by then, so an admin gives each tester a clearly
labelled **sandbox test earning** on one of their published reviews. The tester
then withdraws it through the real cashout flow, and an admin pays it through
**PayPal sandbox**. No real money moves at any point.

Code: `backend/app/services/qa_sandbox_service.py`,
`backend/app/services/payout_service.py`, migrations `0058`/`0059`; console
screens **QA Payments** (`/moderate/qa-sandbox`) and **Payouts**
(`/moderate/payouts`). Tests: `backend/tests/test_qa_sandbox_payouts_api.py`,
`e2e/qa-payments.spec.ts`.

## The rules that keep it safe

| Rule | How it is enforced |
|---|---|
| Only accounts the owner names | The tester list (`platform_settings.qa_testers`) is changed only by the site owner (`require_root_owner`). A moderator can credit a tester, never make someone one. Claimed seller accounts are refused. |
| Never real money | Refused while `PAYOUT_PROVIDER=paypal_live`. A live batch leaves out anyone holding test money. In sandbox mode nothing is sent unless the PayPal host is the sandbox host. |
| One per review, capped | ₱350 by default (enough for the ₱300 minimum), ₱1–₱1,000. A partial unique index allows one test earning per review. Only a published original review qualifies. |
| Never revenue | A test earning is an ordinary ledger row with `is_test = true`, 100% to the tester, **no platform share and no Honesty Fund share** (database CHECK). Revenue, affiliate and Honesty Fund figures filter it out. |
| Visible and audited | The tester is notified ("QA only — not real money") and the earning shows as **Sandbox test** in their history. Naming/removing a tester, each credit, and every payout step (sent, paid, failed, cancelled, retried) write an audit entry with the admin's id. |

## Step by step

### 1. Site owner — name the testers (once)

1. Sign in as the site owner and open **Admin → Finance → QA Payments**.
2. Under **QA testers**, enter each tester's username (`@handle`) or email and
   press **Add tester**. Only these accounts can receive test earnings.
3. Remove a tester with **Remove tester** when testing ends. Earnings already
   credited stay in the ledger (history is never deleted); no new ones can be
   given.

**Named on production (owner request, 2026-09-28):** `@bluntly_ph`
(bluntly.ph@gmail.com) — audit entry `qa_tester_add`. It is also the site owner
and a moderator, so that one account can walk every step below itself: publish
a review, save a PayPal **sandbox** email, credit the review on **QA Payments**,
withdraw, then pay it from **Payouts**. The account has no published review yet,
so step 2.1 comes first.

### 2. QA tester — get ready

1. Sign up / sign in on www.bluntly.ph and **publish one review** (any product).
2. Open **Dashboard → Transfer**. Under **Where the money goes**, save a
   **PayPal sandbox** email address. Use a *personal* sandbox account from
   developer.paypal.com → Sandbox → Accounts (so you can sign in to
   sandbox.paypal.com and see the money arrive). Any email works if the admin
   pays by hand.
3. Tell the admin your username.

### 3. Admin — credit the test earning

1. **Admin → Finance → QA Payments**: each tester is listed with their
   published reviews.
2. Next to a review, leave the amount empty for ₱350 (or type ₱1–₱1,000) and
   press **Credit test earning**. The row changes to "Test earning ₱… credited".

### 4. QA tester — withdraw it

1. You get a notification: "Sandbox test earning: ₱350.00 for QA".
2. **Dashboard → Transfer** shows a *You're a QA tester* note; **Ready to
   withdraw** now includes the test earning, and the earning appears below as
   **Sandbox test · QA test earning · not real money**.
3. Press **Request Withdrawal**. It appears under **Your withdrawals** as
   "Requested · in the batch for …".

### 5. Admin — pay it

1. **Admin → Finance → Payouts**. The top card says how payouts are sent:
   * **PayPal API: Configured (sandbox host)** — press **Send to PayPal
     sandbox**; the requests move to **With PayPal**. Press **Check PayPal ·
     batch_…** until they settle as paid (or failed, which refunds the tester).
   * **PayPal API: Not configured** — pay each request from the PayPal sandbox
     dashboard (sandbox.paypal.com, the business sandbox account) to the
     PayPal address shown on the row, then press **Mark paid** and paste the
     sandbox transaction ID.
2. **Mark failed** (with a reason the tester will see) or **Cancel** puts the
   money back in the tester's balance; **Retry** re-queues a failed one.

### 6. QA tester — confirm

1. Notification: "Your ₱350.00 withdrawal was paid", with the reference.
2. **Transfer → Your withdrawals** shows "Paid <date>" and the reference.
3. With the PayPal API route, the sandbox personal account shows the payment
   at sandbox.paypal.com.

## What testers should check and report

* The test earning is labelled as a test everywhere it appears, and nowhere
  suggests it is real income.
* Withdrawal is refused below ₱300 and without a PayPal address, with a clear
  reason.
* A second withdrawal right after the first is accepted (no waiting period).
* Failed and cancelled withdrawals return the money to the balance and say why.
* A non-tester account never sees the QA note and cannot be credited.

## Real earnings (for comparison)

Real money follows the same payout steps, but reaches the balance differently:
**Affiliate Links → Import a marketplace report** (Shopee/Lazada CSV, preview
first) credits each attributed sale 40% to its reviewer as *still clearing*;
**Record a marketplace payout** for that platform and month clears it; only
then can the reviewer withdraw. PayPal stays SANDBOX.
