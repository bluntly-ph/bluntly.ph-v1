"""Reused review photos (QA, 2026-09-29): layer 1 of image plagiarism.

The internal check needs no outside provider. Every public review photo is
fingerprinted when it is uploaded (`image_fingerprint`, table
`image_fingerprints`); when a review is published with a photo, or its one
72-hour photo swap happens (§4), that photo is compared with the photos of
every EARLIER review on the platform:

* the same bytes (SHA-256), or
* a difference hash within `NEAR_DISTANCE` bits (a resized, re-encoded,
  lightly cropped or brightened copy).

A match files one SYSTEM_DETECTED `duplicate_image` report on the later review,
with ids and distances as evidence. Like every integrity signal it removes
nothing, blocks nothing, touches no money and is shown only to staff; the
check runs after the review is committed and any failure is logged and
dropped (§12).

Layer 2, a search of the WEB for the photo (reverse image search), needs an
outside provider. None is procured: `integrity_checks.IMAGE_ADAPTERS` is empty
and the queue says "not_configured" (ADR-007). That is a blocker recorded, not
a check pretended.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import BigInteger, cast, func, literal, select
from sqlalchemy.dialects.postgresql import BIT
from sqlalchemy.orm import Session

from app.models.enums import ModerationReason, ModerationTargetType
from app.models.integrity import ImageFingerprint
from app.models.review import Review
from app.services import image_fingerprint
from app.services.image_fingerprint import ALGORITHM_VERSION, NEAR_DISTANCE, Fingerprint

log = logging.getLogger(__name__)

SIGNAL = "duplicate_image"
SEVERITY = 0.8


def record_upload(db: Session, *, url: str, uploader_id: uuid.UUID | None,
                  fp: Fingerprint) -> None:
    """Store the fingerprint of a photo just uploaded. The caller commits."""
    db.add(ImageFingerprint(url=url, uploader_id=uploader_id, sha256=fp.sha256,
                            dhash=fp.dhash_signed, width=fp.width, height=fp.height,
                            algorithm=ALGORITHM_VERSION))


@dataclass(frozen=True)
class ImageFinding:
    matched_review_id: uuid.UUID
    distance: int
    identical: bool
    others: tuple[tuple[uuid.UUID, int], ...] = ()

    def evidence(self, detected_at: datetime) -> dict:
        return {
            "matched_review": str(self.matched_review_id),
            "distance": self.distance,
            "hash_bits": image_fingerprint.HASH_BITS,
            "identical_file": self.identical,
            "other_matches": [{"id": str(i), "distance": d} for i, d in self.others],
            "algorithm": ALGORITHM_VERSION,
            "threshold": NEAR_DISTANCE,
            "detected_at": detected_at.isoformat(),
        }


#: Near fingerprints looked at per check. One photo reused hundreds of times
#: still yields its closest and earliest matches; the rest add no evidence.
CANDIDATES = 50


def review_image_duplicate(db: Session, review: Review) -> ImageFinding | None:
    """The closest earlier review whose photo is the same picture, if any.

    Two short queries rather than one join. Postgres cannot estimate how few
    fingerprints pass the Hamming filter, so a join hashed every review first:
    141 ms at 50,000 photos. Filtering the fingerprints (one pass, ~11 ms) and
    then reading the few reviews by `ix_reviews_photo_url` (0069) costs about
    11 ms in all (docs/ANTI_FARMING_AND_PLAGIARISM.md)."""
    if not review.photo_url:
        return None
    mine = db.scalar(select(ImageFingerprint).where(ImageFingerprint.url == review.photo_url))
    if mine is None:
        return None       # uploaded before fingerprints existed: nothing to compare
    # Hamming distance in SQL: XOR the two BIGINTs, count the set bits
    # (Postgres 14+ `bit_count`).
    distance_expr = func.bit_count(cast(
        ImageFingerprint.dhash.op("#")(literal(int(mine.dhash), BigInteger)), BIT(64)))
    near = {url: (sha, int(d)) for url, sha, d in db.execute(
        select(ImageFingerprint.url, ImageFingerprint.sha256, distance_expr)
        # Its own URL included: the same upload on another of the member's
        # reviews is a reused photo too. Only its own thread is excused, below.
        .where((ImageFingerprint.sha256 == mine.sha256) | (distance_expr <= NEAR_DISTANCE))
        .order_by(distance_expr, ImageFingerprint.url)
        .limit(CANDIDATES))}
    if not near:
        return None
    root = func.coalesce(Review.thread_id, Review.id)
    reviews = db.execute(
        select(Review.id, Review.photo_url, Review.created_at)
        .where(Review.photo_url.in_(list(near)),
               Review.id != review.id,
               Review.is_removed.is_(False),
               Review.created_at < review.created_at,
               # A dated update reusing its own thread's photo is not a copy (§4).
               root != (review.thread_id or review.id))).all()
    if not reviews:
        return None

    def distance(url: str) -> int:
        sha, d = near[url]
        return 0 if sha == mine.sha256 else d

    ranked = sorted(reviews, key=lambda r: (distance(r.photo_url), r.created_at, r.id))[:3]
    best, *rest = ranked
    return ImageFinding(
        matched_review_id=best.id,
        distance=distance(best.photo_url),
        identical=near[best.photo_url][0] == mine.sha256,
        others=tuple((r.id, distance(r.photo_url)) for r in rest))


def check_review_photo(db: Session, review_id: uuid.UUID) -> None:
    """Best effort, after the review is committed; never raises."""
    try:
        review = db.get(Review, review_id)
        if review is None or review.is_removed:
            return
        finding = review_image_duplicate(db, review)
        if finding is not None:
            from app.services.report_service import file_system_report
            report, created = file_system_report(
                db, target_type=ModerationTargetType.review, target_ref=review.id,
                signal=SIGNAL, reason=ModerationReason.fake_proof, severity=SEVERITY)
            if created:
                report.context = {**(report.context or {}),
                                  "evidence": finding.evidence(datetime.now(UTC))}
        db.commit()
    except Exception:  # noqa: BLE001 - a check must never break a submission
        db.rollback()
        log.warning("duplicate image check failed", extra={"extra_fields": {
            "review": str(review_id)}}, exc_info=True)
