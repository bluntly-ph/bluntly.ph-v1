"""Publish reviews that were held under the old hide-until-approved flow.

Since 2026-09-22 a review is public from submission (confirmed by Zient) and
`published_at` means "when it went public", i.e. its submission. Reviews
submitted before the change and never decided are still unpublished, waiting
for a moderator's publish that no longer exists. This makes them what they
would have been: public since they were submitted.

Selected, and only these: unpublished, not removed, `earn_eligible_status =
pending`, never taken down (no `unpublish` audit row), never rejected (no
`reject` audit row — under the old flow an author's edit re-queued a rejected
review as `pending` while it stayed hidden, so the status alone does not
prove nobody decided it), and not written by a suspended account. Anything a
moderator acted on stays exactly as it is. Earning state is not touched —
selected reviews stay `pending` in the earn_eligible queue.

Dry run by default. Rewriting rows is a guarded script, never a migration
(docs/ENVIRONMENTS.md, "Destructive data").

    cd backend && python -m scripts.backfill_public_on_submit                 # dry run
    cd backend && python -m scripts.backfill_public_on_submit --apply         # test DB
    cd backend && python -m scripts.backfill_public_on_submit --apply --allow-production
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.core.env_guard import guard_cli
from app.db.session import SessionLocal
from app.models.enums import EarnEligibleStatus, ModerationAction
from app.models.moderation import ModerationLog
from app.models.review import Review
from app.models.user import User


def held_reviews(db):
    decided = select(ModerationLog.id).where(
        ModerationLog.target_ref == Review.id,
        ModerationLog.action.in_([ModerationAction.unpublish, ModerationAction.reject,
                                  ModerationAction.remove])).exists()
    suspended = select(User.id).where(User.id == Review.author_id,
                                      User.is_suspended.is_(True)).exists()
    return list(db.scalars(select(Review).where(
        Review.published_at.is_(None),
        Review.is_removed.is_(False),
        Review.earn_eligible_status == EarnEligibleStatus.pending,
        ~decided,
        ~suspended,
    ).order_by(Review.created_at)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()
    from app.services.review_service import recompute_product_aggregates
    from app.services.trust_service import recompute_user_trust

    db = SessionLocal()
    try:
        rows = held_reviews(db)
        print(f"{len(rows)} held review(s) would become public at their submission time")
        for r in rows[:20]:
            print(f"  {r.id}  submitted {r.created_at:%Y-%m-%d}  {r.title[:60]!r}")
        if not args.apply:
            print("dry run — nothing written (pass --apply to publish them)")
            return
        for r in rows:
            r.published_at = r.created_at
        db.flush()
        for pid in {r.product_id for r in rows}:
            recompute_product_aggregates(db, pid)
        for aid in {r.author_id for r in rows if r.author_id}:
            recompute_user_trust(db, aid)
        db.commit()
        print(f"published {len(rows)} review(s)")
    finally:
        db.close()


if __name__ == "__main__":
    guard_cli("backfill_public_on_submit", production_is_legitimate=True)
    main()
