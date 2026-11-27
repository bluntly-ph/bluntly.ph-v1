"""One-click unsubscribe from the emails (0085; RFC 8058).

Each notification and weekly summary carries a signed link for one channel
(`email_outbox_service.unsubscribe_token`): `email` (store notices by email) or
`weekly_summary`. No sign-in: the token is the proof, and all it can do is turn
that one channel off for that one account.

  GET   reads the link: which channel it turns off and whether it is still on.
        Changes nothing, because mail scanners and link previews fetch GETs.
  POST  turns it off. Mail apps POST here from the List-Unsubscribe header
        (body "List-Unsubscribe=One-Click", ignored); the /unsubscribe page
        POSTs from its button.

A bad, tampered or orphaned token is one 404, so a link reveals nothing about
whether an account exists. Turning the channel back on is the Settings switch.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.rate_limit import enforce_rate_limit
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Problem
from app.services import email_outbox_service, notification_service

router = APIRouter(prefix="/email", tags=["email"])


class UnsubscribeOut(BaseModel):
    scope: Literal["email", "weekly_summary"]
    subscribed: bool


def _owner(db: Session, token: str) -> tuple[User, str]:
    found = email_outbox_service.read_unsubscribe_token(token)
    user = db.get(User, found[0]) if found else None
    if user is None:
        raise NotFoundError("This unsubscribe link isn't valid.")
    return user, found[1]


@router.get("/unsubscribe", response_model=UnsubscribeOut,
            responses={404: {"model": Problem}, 429: {"model": Problem}},
            summary="What an unsubscribe link turns off (changes nothing)")
def read_unsubscribe(request: Request, token: str = Query(..., max_length=200),
                     db: Session = Depends(get_db)) -> UnsubscribeOut:
    enforce_rate_limit(request, "email_unsubscribe")
    user, scope = _owner(db, token)
    return UnsubscribeOut(scope=scope, subscribed=notification_service.prefs_of(user)[scope])


@router.post("/unsubscribe", response_model=UnsubscribeOut,
             responses={404: {"model": Problem}, 429: {"model": Problem}},
             summary="Turn one email channel off from a signed link (RFC 8058 one-click)")
def unsubscribe(request: Request, token: str = Query(..., max_length=200),
                db: Session = Depends(get_db)) -> UnsubscribeOut:
    enforce_rate_limit(request, "email_unsubscribe")
    user, scope = _owner(db, token)
    prefs = notification_service.prefs_of(user)
    if prefs[scope]:
        prefs[scope] = False
        user.notification_prefs = prefs
        db.commit()
    return UnsubscribeOut(scope=scope, subscribed=False)
