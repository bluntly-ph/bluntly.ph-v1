"""Traffic geography ingest. Written by our own proxy, read by moderators.

WHY THIS EXISTS AS AN ENDPOINT. The only place that sees a genuine visitor
request is the Next.js proxy: server-rendered pages call the API through
`lib/api/client.ts`, which builds its headers from scratch and forwards none of
the visitor's, so a backend that simply read its own request headers would
record the location of the Vercel FUNCTION on every page render — a chart
showing thousands of visits from our own datacenter. The proxy therefore
normalises the edge headers where they are real and posts the result here.

TRUST MODEL. Only our proxy may write here. Review views feed the admin's
monetization attention list (services/monetization_attention.py), so a forged
view is not a skewed chart but a nudge on who gets attention, and an open
endpoint let anyone post them. The proxy presents TRAFFIC_BEACON_SECRET in
`X-Traffic-Key` (compared in constant time, the telemetry endpoint's pattern);
in production an unset secret refuses everything rather than accepting
everyone. A browser-sent beacon could not hold the secret, which is why the
beacon stays in the proxy.

It is rate limited per visitor: the proxy forwards the visitor's address
signed (lib/client-ip-signature.ts), because the address this request arrives
from is the proxy's own and is shared by everyone.

Beyond that, the bounds that always applied still do:

  * the only reachable effect is incrementing a counter in an aggregate table
  * nothing here reads back, so it cannot be used to learn anything
  * no field accepts free text that is ever rendered as markup
  * values are validated to shape, so it cannot store arbitrary content
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, AuthError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import get_optional_user, is_staff
from app.db.session import get_db
from app.models.review import Review
from app.models.user import User
from app.services import request_traffic_service
from app.services.request_geo import RequestGeo

router = APIRouter(prefix="/internal", tags=["internal: traffic"])


class TrafficBeacon(BaseModel):
    """One request's resolved location, as the proxy read it from the edge."""

    country: str | None = Field(default=None, max_length=2)
    region: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=128)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    pop: str | None = Field(default=None, max_length=8)
    #: Set when the request the proxy saw was a review page. A view is the same
    #: event as the page request, so it costs no extra beacon.
    review_id: uuid.UUID | None = None

    @field_validator("country")
    @classmethod
    def _iso_alpha2(cls, value: str | None) -> str | None:
        """Two letters or nothing. Keeps the country dimension a country."""
        if value is None:
            return None
        value = value.strip().upper()
        return value if len(value) == 2 and value.isalpha() else None

    @field_validator("pop")
    @classmethod
    def _pop_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        return value if value.isalnum() else None

    @field_validator("region", "city")
    @classmethod
    def _place_name(cls, value: str | None) -> str | None:
        """A trimmed place name, or nothing.

        Markup and control characters are dropped rather than stored. They can
        never execute — the values are parameterised into Postgres and escaped
        by React on the way out, and that was verified against production — but
        a chart is read by a person, and "<script>alert(1)</script>" sitting in
        a ranked list of cities is noise in the one place this data is meant to
        be legible. Anything else is kept: real place names carry accents,
        apostrophes and non-Latin scripts, and an allowlist would quietly drop
        most of the world.
        """
        value = (value or "").strip()
        if not value or any(c in value for c in "<>") or any(ord(c) < 32 for c in value):
            return None
        return value


def _require_beacon_key(presented: str | None) -> None:
    """The proxy's secret, or nothing is recorded.

    Unset outside production, the endpoint stays open so a local stack and the
    test suite need no secret. Unset in production, it fails closed.
    """
    configured = settings.traffic_beacon_secret
    if not configured.strip():
        if settings.is_production:
            raise AuthError("Missing or invalid traffic beacon key.")
        return
    supplied = presented or ""
    if not supplied or not secrets.compare_digest(configured.encode(), supplied.encode()):
        raise AuthError("Missing or invalid traffic beacon key.")


@router.post("/traffic", status_code=status.HTTP_204_NO_CONTENT,
             summary="Record one request's aggregate geography")
def ingest(beacon: TrafficBeacon, request: Request,
           db: Session = Depends(get_db),
           x_traffic_key: str | None = Header(default=None, alias="X-Traffic-Key"),
           ) -> Response:
    """Increment the (hour x location) bucket for one request.

    Returns 204 in every non-rate-limited case, including when the location was
    unusable. The caller is a fire-and-forget beacon that cannot act on an
    error, and answering it with a 4xx would only turn an untracked page view
    into a logged exception on a page that rendered perfectly well. A missing
    or wrong key is the exception: 401, because that caller is not our proxy.
    """
    _require_beacon_key(x_traffic_key)
    enforce_rate_limit(request, "traffic_ingest",
                       max_requests=settings.traffic_rate_limit_max, window_seconds=60)
    geo = RequestGeo(
        country=beacon.country, region=beacon.region, city=beacon.city,
        latitude=beacon.latitude, longitude=beacon.longitude, pop=beacon.pop,
    )
    wrote = request_traffic_service.record(db, geo)

    if beacon.review_id is not None and _is_operational_view(request, db, beacon.review_id):
        # The author re-reading their own review, or a moderator opening it to
        # do their job, is not attention from readers — and these counts feed
        # the admin's momentum facts. The request still counts as traffic.
        pass
    elif beacon.review_id is not None:
        try:
            request_traffic_service.record_view(db, beacon.review_id)
            wrote = True
        except IntegrityError:
            # A review id that does not exist — a stale link, or someone
            # posting a made-up one. The foreign key refuses it, and that is
            # the correct outcome; the page request itself still counts.
            db.rollback()
            wrote = request_traffic_service.record(db, geo)

    if wrote:
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _viewer(request: Request, db: Session) -> User | None:
    """The signed-in reader, when the proxy forwarded their session.

    Never raises: an expired or malformed token must not cost a real view, so a
    failed resolution is simply an anonymous reader.
    """
    try:
        return get_optional_user(request, db)
    except AppError:
        return None


def _is_operational_view(request: Request, db: Session, review_id: uuid.UUID) -> bool:
    viewer = _viewer(request, db)
    if viewer is None:
        return False
    if is_staff(viewer):
        return True
    author_id = db.scalar(select(Review.author_id).where(Review.id == review_id))
    return author_id is not None and author_id == viewer.id
