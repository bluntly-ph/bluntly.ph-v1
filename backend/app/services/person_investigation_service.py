"""People investigation (Figma Screen/Admin/People/Person and its tabs, meeting
2026-10-02, 12:50-15:50): everything an administrator needs to judge one
member, from what the platform already records.

  votes          the member's own votes in the window, per day, with the
                 busiest day called out when it stands far above the rest
  interactions   per other member: the votes and comments this member gave
                 their content, the up-votes they gave back, the share of this
                 member's votes they received, and a reciprocity figure
  activity       votes, comments, reviews, questions, answers and reports,
                 newest first, each linking to the exact thread or comment
  reports        filed by this member, and filed against them or their content
  moderation     staff actions on the member or their reviews
  signals        report and moderation tallies, earnings, linked accounts

RECIPROCITY of a pair is 2·min(a, b)/(a + b) as a percentage, where a is this
member's up-votes on the other's content and b the other's up-votes on this
member's: 0 when it is one-way, 100 when every up-vote is returned. The meeting
reads about 20% as normal and 50-100% as vote trading.

LINKED ACCOUNTS are only what is recorded. Two links exist:

  shared network   another account up-voted from the same keyed network hash
                   (vote_network_fingerprints; 30-day retention, no address)
  shared payout    another account's payout destination is identical (the
                   destination itself is never returned)

There is no device fingerprint anywhere in this product, so no "same device"
link is ever produced.
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.comment import ReviewComment
from app.models.enums import (
    ModerationAction,
    ModerationTargetType,
    ReportResolution,
    VoteDirection,
)
from app.models.integrity import VoteNetworkFingerprint
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.qa import Answer, Question
from app.models.review import Review
from app.models.user import User
from app.models.vote import ReviewVote

MANILA = ZoneInfo("Asia/Manila")
ZERO = Decimal("0")

#: Rows per list; the page shows the newest, the counts are over everything.
LIST_LIMIT = 100
#: A day is a spike when it has at least this many votes and is at least
#: SPIKE_FACTOR times the median day of the window.
SPIKE_MIN_VOTES = 5
SPIKE_FACTOR = 3
#: Staff actions that took content or the account down.
TAKEDOWN_ACTIONS = {ModerationAction.unpublish, ModerationAction.remove, ModerationAction.suspend}


@dataclass
class PersonRef:
    id: uuid.UUID
    name: str
    username: str | None
    trust_stage: int
    trust_level_name: str | None


@dataclass
class Interaction:
    person: PersonRef
    up: int = 0
    down: int = 0
    comments: int = 0
    #: Up-votes the other member gave this member's content.
    up_back: int = 0
    #: Days on which both up-voted the other's content.
    same_day: int = 0
    share_pct: float = 0.0
    reciprocity_pct: float = 0.0
    same_network: bool = False
    last_at: datetime | None = None


@dataclass
class ActivityItem:
    kind: str
    at: datetime
    #: "Upvoted a review", "Commented on a review"...; `subtitle` names the product.
    title: str
    subtitle: str | None
    #: Whose content it was (the reviewed author), when someone else's.
    other: PersonRef | None
    href: str | None


@dataclass
class ReportRow:
    id: uuid.UUID
    direction: str  # "filed" | "received"
    reason: str | None
    target_type: str | None
    target_label: str
    other: PersonRef | None
    status: str  # "open" | "upheld" | "dismissed" | "restored" | "escalated"
    at: datetime
    href: str | None
    notes: str | None


@dataclass
class ModerationRow:
    id: uuid.UUID
    action: str
    target_type: str | None
    target_label: str
    moderator: str | None
    reason: str | None
    notes: str | None
    at: datetime


@dataclass
class LinkedAccount:
    person: PersonRef
    basis: str  # "shared_network" | "shared_payout_account"
    detail: str


@dataclass
class Investigation:
    person: User
    status: str
    days: int
    votes_total: int
    votes_up: int
    votes_down: int
    daily: list[tuple[date, int, int]]
    spike: tuple[date, int] | None
    interactions: list[Interaction]
    interactions_total: int
    top3_share_pct: float
    activity: list[ActivityItem]
    activity_total: int
    reports: list[ReportRow]
    reports_filed: int
    reports_filed_upheld: int
    reports_against: int
    reports_against_upheld: int
    moderation: list[ModerationRow]
    takedowns: int
    earned: Decimal | None
    pending: Decimal | None
    linked: list[LinkedAccount] = field(default_factory=list)


def _ref(user: User | None) -> PersonRef | None:
    if user is None:
        return None
    return PersonRef(id=user.id, name=user.display_name or user.username or "Member",
                     username=user.username, trust_stage=user.trust_stage,
                     trust_level_name=user.trust_level_name)


def _manila_day(moment: datetime) -> date:
    return moment.astimezone(MANILA).date()


def _status(user: User) -> str:
    if user.is_suspended:
        return "suspended"
    if user.is_under_investigation:
        return "investigating"
    return "active"


def _report_status(log: ModerationLog) -> str:
    if log.resolution is None:
        return "open"
    return {
        ReportResolution.content_removed: "upheld",
        ReportResolution.dismissed: "dismissed",
        ReportResolution.content_restored: "restored",
        ReportResolution.escalated: "escalated",
    }.get(log.resolution, str(log.resolution))


def investigate(db: Session, user_id: uuid.UUID, *, days: int = 30,
                now: datetime | None = None) -> Investigation:
    person = db.get(User, user_id)
    if person is None:
        raise AppError("No member has that id.", code="person_not_found", status_code=404,
                       title="Not found")
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    uid = person.id

    # --- this member's reviews, and who wrote the reviews they voted on --------
    my_review_ids = set(db.scalars(select(Review.id).where(Review.author_id == uid)))

    my_votes = db.execute(
        select(ReviewVote.review_id, ReviewVote.vote, ReviewVote.created_at,
               Review.author_id, Review.product_id)
        .join(Review, Review.id == ReviewVote.review_id)
        .where(ReviewVote.voter_id == uid)
        .order_by(ReviewVote.created_at.desc())
    ).all()

    # Votes in the window, per Manila day.
    window = [v for v in my_votes if v.created_at >= since]
    up = sum(1 for v in window if v.vote == VoteDirection.up)
    per_day: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    for v in window:
        per_day[_manila_day(v.created_at)][0 if v.vote == VoteDirection.up else 1] += 1
    first_day = _manila_day(since)
    daily = []
    for n in range(days + 1):
        d = first_day + timedelta(days=n)
        u, dn = per_day.get(d, [0, 0])
        daily.append((d, u, dn))
    totals = [u + dn for _, u, dn in daily]
    spike = None
    if totals:
        busiest = max(range(len(daily)), key=lambda i: totals[i])
        median = statistics.median(totals)
        if totals[busiest] >= SPIKE_MIN_VOTES and totals[busiest] >= SPIKE_FACTOR * max(median, 1):
            spike = (daily[busiest][0], totals[busiest])

    # --- interactions --------------------------------------------------------
    pairs: dict[uuid.UUID, Interaction] = {}
    up_days: dict[uuid.UUID, set[date]] = defaultdict(set)
    people_ids: set[uuid.UUID] = set()

    def pair(other_id: uuid.UUID) -> Interaction:
        if other_id not in pairs:
            pairs[other_id] = Interaction(person=PersonRef(other_id, "", None, 0, None))
            people_ids.add(other_id)
        return pairs[other_id]

    for v in my_votes:
        if v.author_id is None or v.author_id == uid:
            continue
        p = pair(v.author_id)
        if v.vote == VoteDirection.up:
            p.up += 1
            up_days[v.author_id].add(_manila_day(v.created_at))
        else:
            p.down += 1
        p.last_at = max(p.last_at, v.created_at) if p.last_at else v.created_at

    my_comments = db.execute(
        select(ReviewComment.id, ReviewComment.review_id, ReviewComment.created_at,
               Review.author_id, Review.product_id)
        .join(Review, Review.id == ReviewComment.review_id)
        .where(ReviewComment.author_id == uid, ReviewComment.is_removed.is_(False))
        .order_by(ReviewComment.created_at.desc())
    ).all()
    for c in my_comments:
        if c.author_id is None or c.author_id == uid:
            continue
        p = pair(c.author_id)
        p.comments += 1
        p.last_at = max(p.last_at, c.created_at) if p.last_at else c.created_at

    if my_review_ids:
        back = db.execute(
            select(ReviewVote.voter_id, ReviewVote.created_at)
            .where(ReviewVote.review_id.in_(my_review_ids),
                   ReviewVote.vote == VoteDirection.up,
                   ReviewVote.voter_id != uid)
        ).all()
        for voter_id, at in back:
            if voter_id in pairs:
                pairs[voter_id].up_back += 1
                if _manila_day(at) in up_days[voter_id]:
                    pairs[voter_id].same_day += 1

    my_networks = set(db.scalars(
        select(VoteNetworkFingerprint.network).where(VoteNetworkFingerprint.voter_id == uid)))
    network_peers: dict[uuid.UUID, int] = {}
    if my_networks:
        network_peers = dict(db.execute(
            select(VoteNetworkFingerprint.voter_id,
                   func.count(func.distinct(VoteNetworkFingerprint.network)))
            .where(VoteNetworkFingerprint.network.in_(my_networks),
                   VoteNetworkFingerprint.voter_id != uid)
            .group_by(VoteNetworkFingerprint.voter_id)
        ).all())

    payout_peers: list[uuid.UUID] = []
    if person.payout_account:
        payout_peers = list(db.scalars(
            select(User.id).where(User.payout_account == person.payout_account, User.id != uid)))

    others = people_ids | set(network_peers) | set(payout_peers)
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(others)))} if others else {}

    total_votes = len(my_votes) or 1
    for other_id, p in pairs.items():
        ref = _ref(users.get(other_id))
        if ref:
            p.person = ref
        p.share_pct = round((p.up + p.down) / total_votes * 100, 1) if my_votes else 0.0
        a, b = p.up, p.up_back
        p.reciprocity_pct = round(2 * min(a, b) / (a + b) * 100, 1) if a + b else 0.0
        p.same_network = other_id in network_peers
    interactions = sorted(pairs.values(),
                          key=lambda p: (p.up + p.down + p.comments, p.last_at or since),
                          reverse=True)
    top3 = sum(p.share_pct for p in sorted(pairs.values(), key=lambda p: -p.share_pct)[:3])

    # --- activity --------------------------------------------------------------
    review_rows = {r.id: r for r in db.scalars(select(Review).where(
        Review.id.in_({v.review_id for v in my_votes} | {c.review_id for c in my_comments}
                      | my_review_ids)))} if (my_votes or my_comments or my_review_ids) else {}
    product_names = dict(db.execute(select(Product.id, Product.canonical_name).where(
        Product.id.in_({r.product_id for r in review_rows.values() if r.product_id})))
        .all()) if review_rows else {}
    author_ids = {r.author_id for r in review_rows.values() if r.author_id}
    authors = ({u.id: u for u in db.scalars(select(User).where(User.id.in_(author_ids)))}
               if author_ids else {})

    def whose(review_id: uuid.UUID) -> str:
        r = review_rows.get(review_id)
        if r is None:
            return "a removed review"
        owner = authors.get(r.author_id) if r.author_id else None
        product = product_names.get(r.product_id) or "a product"
        name = (owner.display_name or owner.username) if owner else "a former member"
        return f"{name}'s review of {product}"

    def about(review_id: uuid.UUID) -> tuple[str | None, PersonRef | None]:
        r = review_rows.get(review_id)
        if r is None:
            return None, None
        owner = authors.get(r.author_id) if r.author_id else None
        return product_names.get(r.product_id), _ref(owner)

    activity: list[ActivityItem] = []
    for v in my_votes[:LIST_LIMIT]:
        verb = "Upvoted a review" if v.vote == VoteDirection.up else "Downvoted a review"
        product, owner = about(v.review_id)
        activity.append(ActivityItem(f"vote_{v.vote.value}", v.created_at, verb, product, owner,
                                     f"/reviews/{v.review_id}"))
    for c in my_comments[:LIST_LIMIT]:
        product, owner = about(c.review_id)
        activity.append(ActivityItem("comment", c.created_at, "Commented on a review", product,
                                     owner, f"/reviews/{c.review_id}#comment-{c.id}"))
    for rid in list(my_review_ids)[:LIST_LIMIT]:
        r = review_rows.get(rid)
        if r is not None:
            activity.append(ActivityItem("review", r.created_at, "Posted a review",
                                         product_names.get(r.product_id), _ref(person),
                                         f"/reviews/{r.id}"))
    for q in db.scalars(select(Question).where(Question.asker_id == uid)
                        .order_by(Question.created_at.desc()).limit(LIST_LIMIT)):
        activity.append(ActivityItem("question", q.created_at, "Asked a question", q.body[:80],
                                     _ref(person), f"/questions/{q.id}"))
    for a in db.scalars(select(Answer).where(Answer.responder_id == uid)
                        .order_by(Answer.created_at.desc()).limit(LIST_LIMIT)):
        activity.append(ActivityItem("answer", a.created_at, "Answered a question", None, None,
                                     f"/questions/{a.question_id}#answer-{a.id}"))

    # --- reports ---------------------------------------------------------------
    filed = list(db.scalars(
        select(ModerationLog).where(ModerationLog.action == ModerationAction.report,
                                    ModerationLog.reporter_id == uid)
        .order_by(ModerationLog.created_at.desc())))
    my_comment_ids = set(db.scalars(select(ReviewComment.id).where(ReviewComment.author_id == uid)))
    my_answer_ids = set(db.scalars(select(Answer.id).where(Answer.responder_id == uid)))
    my_question_ids = set(db.scalars(select(Question.id).where(Question.asker_id == uid)))
    mine = my_review_ids | my_comment_ids | my_answer_ids | my_question_ids | {uid}
    received = list(db.scalars(
        select(ModerationLog).where(ModerationLog.action == ModerationAction.report,
                                    ModerationLog.target_ref.in_(mine))
        .order_by(ModerationLog.created_at.desc())))
    reporters = {u.id: u for u in db.scalars(select(User).where(
        User.id.in_({r.reporter_id for r in received if r.reporter_id})))} if received else {}

    def target_label(log: ModerationLog) -> tuple[str, str | None]:
        t = log.target_type
        ref = log.target_ref
        if t == ModerationTargetType.review and ref:
            return whose(ref) if ref in review_rows else "a review", f"/reviews/{ref}"
        if t == ModerationTargetType.user:
            return "a member account", None
        return (t.value.replace("_", " ") if t else "content"), None

    for log in filed[:LIST_LIMIT]:
        label, href = target_label(log)
        product, owner = (about(log.target_ref)
                          if log.target_type == ModerationTargetType.review and log.target_ref
                          else (None, None))
        reason = log.reason.value.replace("_", " ") if log.reason else "a report"
        activity.append(ActivityItem("report", log.created_at, f"Reported {reason}",
                                     product or label, owner, href))

    reports: list[ReportRow] = []
    for direction, logs in (("filed", filed), ("received", received)):
        for log in logs[:LIST_LIMIT]:
            label, href = target_label(log)
            other = _ref(person) if direction == "filed" else (
                _ref(reporters.get(log.reporter_id)) if log.reporter_id else None)
            reports.append(ReportRow(
                id=log.id, direction=direction,
                reason=log.reason.value if log.reason else None,
                target_type=log.target_type.value if log.target_type else None,
                target_label=label, other=other, status=_report_status(log),
                at=log.created_at, href=href, notes=log.notes))
    reports.sort(key=lambda r: r.at, reverse=True)

    # --- moderation --------------------------------------------------------------
    staff_rows = list(db.scalars(
        select(ModerationLog).where(
            ModerationLog.action.not_in((ModerationAction.report, ModerationAction.receipt_view)),
            or_(ModerationLog.target_ref.in_(mine),
                ModerationLog.target_ref == uid))
        .order_by(ModerationLog.created_at.desc()).limit(LIST_LIMIT)))
    moderators = {u.id: u for u in db.scalars(select(User).where(
        User.id.in_({m.moderator_id for m in staff_rows if m.moderator_id})))} if staff_rows else {}
    moderation = [
        ModerationRow(
            id=m.id, action=m.action.value,
            target_type=m.target_type.value if m.target_type else None,
            target_label=target_label(m)[0],
            moderator=((moderators[m.moderator_id].display_name
                        or moderators[m.moderator_id].username)
                       if m.moderator_id in moderators else None),
            reason=m.reason.value if m.reason else None, notes=m.notes, at=m.created_at)
        for m in staff_rows
    ]

    # --- earnings (the reviewer's own statement; missing rather than guessed) ---
    earned = pending = None
    try:
        from app.services.reporting import earnings_statement, periods
        summary = earnings_statement.build(db, person, periods.resolve()).summary
        earned = summary.lifetime_earned
        pending = summary.clearing + summary.in_flight
    except Exception:  # noqa: BLE001 - the page stands without its money tile
        db.rollback()

    # --- linked accounts ---------------------------------------------------------
    linked: list[LinkedAccount] = []
    for other_id, shared in sorted(network_peers.items(), key=lambda kv: -kv[1]):
        ref = _ref(users.get(other_id))
        if ref:
            linked.append(LinkedAccount(
                ref, "shared_network",
                f"Voted from {shared} of the same network{'s' if shared != 1 else ''} "
                "in the last 30 days"))
    for other_id in payout_peers:
        ref = _ref(users.get(other_id))
        if ref:
            linked.append(LinkedAccount(ref, "shared_payout_account",
                                        "Uses the same payout account"))

    activity.sort(key=lambda a: a.at, reverse=True)
    return Investigation(
        person=person, status=_status(person), days=days,
        votes_total=len(window), votes_up=up, votes_down=len(window) - up,
        daily=daily, spike=spike,
        interactions=interactions[:LIST_LIMIT], interactions_total=len(interactions),
        top3_share_pct=round(top3, 1),
        activity=activity[:LIST_LIMIT],
        activity_total=(len(my_votes) + len(my_comments) + len(my_review_ids) + len(filed)
                        + len(my_question_ids) + len(my_answer_ids)),
        reports=reports,
        reports_filed=len(filed),
        reports_filed_upheld=sum(1 for r in filed if _report_status(r) == "upheld"),
        reports_against=len(received),
        reports_against_upheld=sum(1 for r in received if _report_status(r) == "upheld"),
        moderation=moderation,
        takedowns=sum(1 for m in staff_rows if m.action in TAKEDOWN_ACTIONS),
        earned=earned, pending=pending, linked=linked,
    )
