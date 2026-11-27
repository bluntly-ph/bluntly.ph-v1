"""Permanently purge EXPLICITLY SELECTED test/seed reviews. Dry run by default.

Owner decision 2026-09-28 (docs/SEEDING_RUNBOOK.md). The team reseeds proper
data and removes old test reviews; this is the safe path for the second half.
There is no "delete all" anywhere: the script only ever deletes the review IDs
a person wrote into a selection file and then confirmed by its digest.

THE FLOW

    1. list      python -m scripts.purge_test_reviews --out selection.tsv
                 Read-only, safe anywhere. Writes every candidate review, whole
                 threads together, one per line. Only the test-suite class is
                 pre-selected; every other class is written commented out.
    2. review    The owner/team reads selection.tsv, comments out anything to
                 keep and uncomments anything else to remove.
    3. check     python -m scripts.purge_test_reviews --select selection.tsv
                 Re-validates every selected line against the database, prints
                 what would be removed, what blocks it, and the digest.
    4. purge     python -m scripts.purge_test_reviews --select selection.tsv \\
                     --actor USR-000001 --confirm <digest> --apply
                 TEST only. All or nothing, in one transaction, audited.

WHAT IS A CANDIDATE — deterministic markers on the AUTHOR's email, never a
guess from the review's text, age or activity:

    test_suite   @example.com          pytest, Playwright fixtures, the
                                       milestone verifier (pre-selected)
    local_seed   @example.ph           scripts/seed.py's sample shopper
    showcase     @showcase.bluntly.ph  scripts/seed_showcase.py's demo authors

A review by any other account is never listed, and is refused at apply time
even if someone types its ID into the file.

WHAT BLOCKS A REVIEW (refused, never silently erased):
  - any commission, honesty fund distribution, affiliate postback or token
    transaction that points at it: payout/accounting evidence. Such a review
    can still be taken down (hidden, recoverable) by an Administrator; this
    script will not delete it.
  - an OPEN report on it or on one of its comments: someone's complaint still
    waiting on a decision. Resolve the report in the console first.

WHAT GOES WITH A REVIEW: its votes, comments, versions, affiliate link and
reading telemetry (their foreign keys cascade), and the price reports made from
it, which are test data too and would otherwise stay in the public price
history with no source. The affected products' counts and ratings are
recomputed. Click sessions and support requests stay, with the link cleared.

WHAT IS KEPT: accounts, products, and everything not selected. Moderation
history (closed reports, decisions) stays: moderation_logs has no FK. Audit
rows are added naming the actor, the review's public ID and title, its class
and the selection digest. Storage objects (photos, receipts) are not touched;
the summary counts them.

PRODUCTION: `--apply` is refused against production, and `--allow-production`
is refused too — `guard_cli` without `production_is_legitimate`. Production
cleanup is the separate reviewed procedure in docs/SEEDING_RUNBOOK.md.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.env_guard import describe_target, guard_cli
from app.db.session import SessionLocal
from app.models.enums import MemberRole, ModerationAction, ModerationTargetType
from app.models.moderation import ModerationLog
from app.models.user import User
from app.services.staff_directory_service import normalise_staff_ref

#: (class, email LIKE pattern, selected by default)
CLASSES: tuple[tuple[str, str, bool], ...] = (
    ("test_suite", "%@example.com", True),
    ("local_seed", "%@example.ph", False),
    ("showcase", "%@showcase.bluntly.ph", False),
)

#: Tables whose rows are payout/accounting evidence about a review.
FINANCIAL: tuple[tuple[str, str], ...] = (
    ("commissions", "SELECT review_id, count(*) FROM commissions "
                    "WHERE review_id = ANY(:ids) GROUP BY review_id"),
    ("honesty_fund_distributions", "SELECT review_id, count(*) FROM honesty_fund_distributions "
                                   "WHERE review_id = ANY(:ids) GROUP BY review_id"),
    ("affiliate_postbacks", "SELECT review_id, count(*) FROM affiliate_postbacks "
                            "WHERE review_id = ANY(:ids) GROUP BY review_id"),
    ("token_transactions", "SELECT ref_id, count(*) FROM token_transactions "
                           "WHERE ref_id = ANY(:ids) GROUP BY ref_id"),
)

HEADER = "# review_id\tpublic_id\tclass\tauthor\tthread_root\ttitle"


@dataclass(frozen=True)
class Candidate:
    id: uuid.UUID
    public_id: str | None
    klass: str
    author: str | None
    thread_root: uuid.UUID
    title: str
    has_receipt: bool
    has_photo: bool


def _class_sql() -> str:
    whens = " ".join(f"WHEN u.email LIKE '{pat}' THEN '{name}'" for name, pat, _ in CLASSES)
    return f"CASE {whens} END"


def candidates(db: Session, ids: Iterable[uuid.UUID] | None = None) -> list[Candidate]:
    """Every review whose author carries a class marker, or just `ids` of them.

    A review whose author has no marker is simply absent from the result — so
    an ID for a real person's review can never become a candidate.
    """
    markers = " OR ".join(f"u.email LIKE '{pat}'" for _, pat, _ in CLASSES)
    sql = f"""
        SELECT r.id, r.review_id, {_class_sql()} AS klass, u.username,
               COALESCE(r.thread_id, r.id) AS root, r.title,
               r.receipt_key IS NOT NULL, r.photo_url IS NOT NULL
          FROM reviews r JOIN users u ON u.id = r.author_id
         WHERE ({markers})
    """
    params: dict = {}
    if ids is not None:
        sql += " AND r.id = ANY(:ids)"
        params["ids"] = list(ids)
    sql += " ORDER BY COALESCE(r.thread_id, r.id), r.created_at"
    return [Candidate(*row) for row in db.execute(text(sql), params).all()]


def financial_blockers(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    blocked: dict[uuid.UUID, list[str]] = {}
    if not ids:
        return blocked
    for table, sql in FINANCIAL:
        for rid, n in db.execute(text(sql), {"ids": ids}).all():
            blocked.setdefault(rid, []).append(f"{n} {table}")
    return blocked


#: Reports still waiting on a decision, on the review itself or on a comment
#: under it. Closed reports are history and do not block.
OPEN_REPORTS = """
    SELECT r.id, count(*) FROM reviews r
      JOIN moderation_logs m ON m.action = 'report' AND m.resolution IS NULL AND (
           (m.target_type = 'review' AND m.target_ref = r.id)
        OR (m.target_type = 'comment' AND m.target_ref IN (
                SELECT c.id FROM review_comments c WHERE c.review_id = r.id)))
     WHERE r.id = ANY(:ids)
     GROUP BY r.id
"""


def blockers(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Everything that refuses a review: money evidence, then open reports."""
    blocked = financial_blockers(db, ids)
    if ids:
        for rid, n in db.execute(text(OPEN_REPORTS), {"ids": ids}).all():
            blocked.setdefault(rid, []).append(f"{n} open report{'s' if n != 1 else ''}")
    return blocked


def digest(ids: Iterable[uuid.UUID]) -> str:
    """The confirmation token: it names exactly this selection and no other."""
    joined = "\n".join(sorted(str(i) for i in ids))
    return hashlib.sha256(joined.encode()).hexdigest()[:12]


def write_listing(rows: list[Candidate], blocked: dict[uuid.UUID, list[str]], out) -> None:
    default = {name: on for name, _, on in CLASSES}
    out.write("# bluntly.ph test/seed review purge selection\n")
    out.write(f"# generated {datetime.now(UTC).isoformat(timespec='seconds')} against: "
              f"{describe_target()}\n")
    out.write("# A line starting with '#' is NOT selected. Uncomment a line to select it.\n")
    out.write("# Select whole threads: a thread's entries are listed together.\n")
    out.write(HEADER + "\n")
    # Pre-select whole threads only: one blocked or opt-in entry keeps its
    # whole thread commented out, so the default file always checks clean.
    threads = _group((c.thread_root, c) for c in rows)
    clean = {root for root, members in threads.items()
             if all(default.get(m.klass, False) and m.id not in blocked for m in members)}
    for c in rows:
        selected = c.thread_root in clean
        prefix = "" if selected else "# "
        note = f"\t[BLOCKED: {', '.join(blocked[c.id])}]" if c.id in blocked else ""
        title = " ".join(c.title.split())[:80]
        out.write(f"{prefix}{c.id}\t{c.public_id or ''}\t{c.klass}\t@{c.author or ''}\t"
                  f"{c.thread_root}\t{title}{note}\n")


def read_selection(path: str) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            first = line.split("\t", 1)[0].strip()
            try:
                ids.append(uuid.UUID(first))
            except ValueError:
                raise SystemExit(f"{path}:{n}: not a review id: {first!r}") from None
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{path}: a review id is selected twice.")
    return ids


@dataclass
class Check:
    selected: list[uuid.UUID]
    found: list[Candidate]
    unknown: list[uuid.UUID]
    blocked: dict[uuid.UUID, list[str]]
    partial_threads: dict[uuid.UUID, list[uuid.UUID]]

    @property
    def ok(self) -> bool:
        return bool(self.selected) and not (self.unknown or self.blocked or self.partial_threads)


def check_selection(db: Session, selected: list[uuid.UUID]) -> Check:
    found = candidates(db, selected)
    found_ids = {c.id for c in found}
    unknown = [i for i in selected if i not in found_ids]
    blocked = blockers(db, list(found_ids))
    # A thread is purged whole or not at all: a lone update left behind would
    # point at nothing, and a lone root deleted would orphan its updates.
    roots = {c.thread_root for c in found}
    members = {} if not roots else _group(db.execute(text(
        "SELECT COALESCE(thread_id, id), id FROM reviews "
        "WHERE COALESCE(thread_id, id) = ANY(:roots)"), {"roots": list(roots)}).all())
    partial = {root: [m for m in ms if m not in found_ids]
               for root, ms in members.items() if any(m not in found_ids for m in ms)}
    return Check(selected, found, unknown, blocked, partial)


def _group(pairs) -> dict:
    out: dict = {}
    for key, value in pairs:
        out.setdefault(key, []).append(value)
    return out


def resolve_actor(db: Session, ref: str) -> User:
    """The Super Admin the purge is attributed to (USR code or email)."""
    staff_ref = normalise_staff_ref(ref)
    user = db.scalar(select(User).where(
        User.staff_ref == staff_ref if staff_ref else func.lower(User.email) == ref.lower()))
    if user is None:
        raise SystemExit(f"--actor {ref!r}: no such account.")
    if not is_super_admin(user):
        raise SystemExit(f"--actor {ref!r} is not a Super Admin. Only a Super Admin may purge.")
    return user


def is_super_admin(user: User) -> bool:
    return user.role == MemberRole.super_admin


def purge(db: Session, chk: Check, actor: User, token: str) -> int:
    now = datetime.now(UTC).isoformat()
    for c in chk.found:
        # moderation_logs has no FK to reviews, so this outlives the row.
        db.add(ModerationLog(
            log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=actor.id,
            action=ModerationAction.remove, target_type=ModerationTargetType.review,
            target_ref=c.id, notes="test/seed data purge",
            context={"event": "test_data_purge", "class": c.klass, "public_id": c.public_id,
                     "title": c.title[:200], "author": c.author, "selection_digest": token,
                     "at": now}))
    db.flush()
    ids = [c.id for c in chk.found]
    products = list(db.scalars(text(
        "SELECT DISTINCT product_id FROM reviews WHERE id = ANY(:ids)"), {"ids": ids}))
    # The price reports made from these reviews are test data too. Left behind
    # (price_history.review_id is ON DELETE SET NULL) they would stay in the
    # public price history with no source.
    prices = db.execute(text("DELETE FROM price_history WHERE review_id = ANY(:ids)"),
                        {"ids": ids}).rowcount
    # Updates first, then roots: `thread_id` is ON DELETE SET NULL, and a root
    # deleted first would briefly turn its updates into roots of their own.
    n = db.execute(text("DELETE FROM reviews WHERE id = ANY(:ids) AND thread_id IS NOT NULL"),
                   {"ids": ids}).rowcount
    n += db.execute(text("DELETE FROM reviews WHERE id = ANY(:ids)"), {"ids": ids}).rowcount
    # Raw deletes skip the service layer, so refresh what it would have: each
    # product's review count, median rating and trust rating.
    from app.services.review_service import recompute_product_aggregates
    for product_id in products:
        recompute_product_aggregates(db, product_id)
    print(f"removed {prices} price reports made from them; "
          f"recomputed {len(products)} products.")
    return n


def _report(chk: Check, token: str) -> None:
    by_class = _group((c.klass, c.id) for c in chk.found)
    print(f"selected: {len(chk.selected)} | valid candidates: {len(chk.found)} "
          + " ".join(f"{k}={len(v)}" for k, v in sorted(by_class.items())))
    print(f"with receipt objects: {sum(c.has_receipt for c in chk.found)} | "
          f"with photos: {sum(c.has_photo for c in chk.found)} (storage is not touched)")
    for i in chk.unknown:
        print(f"  REFUSED {i}: not a review by a test/seed account (or no longer exists)")
    for i, why in chk.blocked.items():
        print(f"  BLOCKED {i}: {', '.join(why)} - resolve open reports first; "
              "take down a review with money history instead")
    for root, missing in chk.partial_threads.items():
        print(f"  PARTIAL THREAD {root}: also select {', '.join(str(m) for m in missing)}")
    print(f"digest: {token}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", metavar="FILE", help="Write the candidate listing here (step 1).")
    ap.add_argument("--select", metavar="FILE", help="A reviewed selection file (steps 3-4).")
    ap.add_argument("--actor", help="The Super Admin running the purge (USR code or email).")
    ap.add_argument("--confirm", help="The digest printed by the check step.")
    ap.add_argument("--apply", action="store_true", help="Delete. Default is a dry run.")
    args = ap.parse_args(argv)

    if args.apply:
        # Refuses production outright; --allow-production is refused as well.
        guard_cli("purge_test_reviews --apply", argv=argv if argv is not None else sys.argv[1:])
        if not (args.select and args.actor and args.confirm):
            print("--apply needs --select, --actor and --confirm.", file=sys.stderr)
            return 2
    else:
        print(f"[env] purge_test_reviews (dry run, read-only) -> {describe_target()}")

    with SessionLocal() as db:
        if not args.select:
            rows = candidates(db)
            blocked = blockers(db, [c.id for c in rows])
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    write_listing(rows, blocked, fh)
                print(f"wrote {len(rows)} candidates to {args.out}")
            else:
                write_listing(rows, blocked, sys.stdout)
            by_class = _group((c.klass, c.id) for c in rows)
            print(f"candidates: {len(rows)} "
                  + " ".join(f"{k}={len(v)}" for k, v in sorted(by_class.items()))
                  + f" | blocked (money evidence or open report): {len(blocked)}",
                  file=sys.stderr)
            return 0

        selected = read_selection(args.select)
        chk = check_selection(db, selected)
        token = digest(selected)
        _report(chk, token)
        if not args.apply:
            print("dry run: nothing deleted." if chk.ok else "dry run: fix the lines above first.")
            return 0 if chk.ok else 1
        if not chk.ok:
            print("refused: the selection is not clean; nothing deleted.", file=sys.stderr)
            return 1
        if args.confirm != token:
            print("refused: --confirm does not match this selection's digest; nothing deleted.",
                  file=sys.stderr)
            return 1
        actor = resolve_actor(db, args.actor)
        deleted = purge(db, chk, actor, token)
        db.commit()
        print(f"purged {deleted} reviews; audited in moderation_logs (selection {token}).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
