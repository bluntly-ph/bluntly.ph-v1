"""Review drafts kept with the account (QA-003). Every function is the caller's own.

Nothing here publishes, validates review content, or touches earning: a draft is
the composer's form state between visits. Its content is checked when it is
published, by the same POST /reviews every review goes through.

Publishing CONSUMES the draft (owner bug report, 2026-10-03: a published
review's draft stayed listed, could be reopened and edited, and publishing it
again was refused as already posted). The publish deletes the product's draft
in its own transaction (`consume`), and a product slot whose draft was saved
no later than the caller's newest entry on that product is consumed whatever
copy turns up afterwards: the composer's debounced autosave landing after the
publish, or another device re-uploading the copy it kept. Such a draft is never
listed and never stored again (409 `draft_published`, so the client drops its
local copy). Work saved AFTER the newest entry — an update being written for
the thread months later — is a live draft as before.
"""

from __future__ import annotations

import json
import re
import uuid

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.review import Review
from app.models.review_draft import ReviewDraft
from app.models.user import User

#: The composer's slot for work begun before a product was picked.
UNPICKED_SLOT = "__no-product__"
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_SLOT = re.compile(rf"^(__no-product__|{_UUID})$")
#: The composer keeps ten; the account keeps the same ten, oldest going first.
MAX_DRAFTS = 10
#: A full draft is a few kilobytes of text; this is a ceiling, not a target.
MAX_PAYLOAD_BYTES = 64 * 1024


def _check_slot(slot: str) -> str:
    if not _SLOT.match(slot):
        raise AppError("A draft slot is a product id or the unpicked marker.",
                       code="invalid_draft_slot", status_code=422)
    return slot


def _product_of(slot: str) -> uuid.UUID | None:
    return None if slot == UNPICKED_SLOT else uuid.UUID(slot)


def _published_ms(db: Session, user_id: uuid.UUID,
                  product_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, uuid.UUID]]:
    """Per product: (ms of the caller's newest entry, that entry's thread), one query.

    Every entry counts, whatever happened to it later: the draft that became it
    was published then, so it is no longer an unfinished review.
    """
    if not product_ids:
        return {}
    rows = db.execute(
        select(Review.product_id, Review.created_at, func.coalesce(Review.thread_id, Review.id))
        .where(Review.author_id == user_id, Review.product_id.in_(product_ids))
        .distinct(Review.product_id)
        .order_by(Review.product_id, Review.created_at.desc())).all()
    return {pid: (int(created.timestamp() * 1000), thread) for pid, created, thread in rows}


def _all_rows(db: Session, user: User) -> list[ReviewDraft]:
    return list(db.scalars(
        select(ReviewDraft).where(ReviewDraft.user_id == user.id)
        .order_by(ReviewDraft.saved_at_ms.desc())))


def list_for(db: Session, user: User) -> list[ReviewDraft]:
    """The caller's unfinished reviews, newest first. Consumed drafts are not unfinished."""
    rows = _all_rows(db, user)
    published = _published_ms(db, user.id, [p for r in rows if (p := _product_of(r.slot))])
    return [r for r in rows
            if (p := _product_of(r.slot)) not in published or r.saved_at_ms > published[p][0]]


def consume(db: Session, author_id: uuid.UUID, product_id: uuid.UUID) -> None:
    """The product's draft became a review (or a thread update): it is not a draft any more.

    Runs inside the publishing transaction and commits with it, so a failed
    submission keeps its draft and a successful one never leaves it behind.
    """
    db.execute(sql_delete(ReviewDraft).where(ReviewDraft.user_id == author_id,
                                             ReviewDraft.slot == str(product_id)))


def save(db: Session, user: User, slot: str, payload: dict, saved_at_ms: int) -> ReviewDraft:
    """Upsert the caller's draft in `slot`. An older save never replaces a newer one."""
    _check_slot(slot)
    if len(json.dumps(payload, separators=(",", ":")).encode()) > MAX_PAYLOAD_BYTES:
        raise AppError("That draft is too large to keep.", code="draft_too_large", status_code=413)
    product_id = _product_of(slot)
    if product_id is not None:
        published = _published_ms(db, user.id, [product_id]).get(product_id)
        if published is not None and saved_at_ms <= published[0]:
            # A copy of work that is already published: the autosave that left
            # just before Publish, or another device's local copy.
            raise AppError("This review is already published.", code="draft_published",
                           status_code=409, title="Conflicting state",
                           extra={"thread_id": str(published[1])})
    # One statement, so two devices saving a new slot at once cannot collide
    # on the unique (user, slot) key; the WHERE keeps the newer save.
    stmt = insert(ReviewDraft).values(
        id=uuid.uuid4(), user_id=user.id, slot=slot, payload=payload, saved_at_ms=saved_at_ms)
    db.execute(stmt.on_conflict_do_update(
        constraint="uq_review_draft_slot",
        set_={"payload": stmt.excluded.payload, "saved_at_ms": stmt.excluded.saved_at_ms,
              "updated_at": func.now()},
        where=stmt.excluded.saved_at_ms >= ReviewDraft.saved_at_ms))
    db.flush()
    # The cap, oldest first — the same rule the composer applies locally.
    for stale in _all_rows(db, user)[MAX_DRAFTS:]:
        db.delete(stale)
    db.commit()
    row = db.scalar(select(ReviewDraft).where(ReviewDraft.user_id == user.id,
                                              ReviewDraft.slot == slot))
    # A save older than the ten kept is accepted and immediately aged out;
    # echo it back rather than failing the request that sent it.
    return row if row is not None else ReviewDraft(
        user_id=user.id, slot=slot, payload=payload, saved_at_ms=saved_at_ms)


def delete(db: Session, user: User, slot: str) -> None:
    """Remove the caller's draft in `slot`. Someone else's slot is simply not found."""
    _check_slot(slot)
    row = db.scalar(select(ReviewDraft).where(ReviewDraft.user_id == user.id,
                                              ReviewDraft.slot == slot))
    if row is None:
        raise NotFoundError("No draft in that slot.")
    db.delete(row)
    db.commit()
