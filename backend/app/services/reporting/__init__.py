"""System reports: the four the product team asked for, from real ledger rows.

    earnings_statement   a reviewer's own statement (per review, cleared vs
                         clearing, cashouts and payouts)
    seller_rating        a claimed store's rating summary over a period
    commission_payout    imported marketplace commissions, their split, their
                         reconciliation and reviewers' payout readiness
    honesty_fund         the fund's inputs for a period; the distribution
                         itself stays "pending formula" (Business Rules §14)

Every figure is read from the database. Nothing here recomputes a financial
split: the 40/30/30 shares were fixed by `earnings.split_for_review` when each
commission was recognised and are stored on the row, so a report reads them
rather than deriving them a second way. Withdrawable balances come from
`payout_service.withdrawable`, the same function a cashout is checked against.

Money is `Decimal` end to end and leaves the API as a string.

Authorization lives in the routes (`app/api/v1/routes/reporting.py`), each
behind one named dependency, so the coming Administrator / Super Admin split
changes a guard and not a report.
"""
