"""Email (0085): the outbox, store notices by email, the Monday summary, and the
one-click unsubscribe.

The outbox is shared by the whole suite (every store notice an earlier test caused
is queued in it), so each test that drains moves its own rows to the front
(`next_attempt_at` in 2000) and drains exactly that many.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.adapters import email as email_adapter
from app.adapters.email import EmailSendError
from app.adapters.email_templates import notification_email
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.email_outbox import EmailOutbox
from app.models.user import User
from app.services import email_outbox_service as outbox
from app.services import weekly_summary_service
from app.services.notification_service import notify
from tests.conftest import make_user, register_and_token, requires_db
from tests.test_seller_console_api import _claimed_store, _rate

pytestmark = requires_db
PREFS = "/api/v1/users/me/notification-prefs"
LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)


class _Sent(list):
    def __init__(self):
        super().__init__()
        self.failing: set[str] = set()


@pytest.fixture
def sent(monkeypatch):
    """Every send the outbox makes: (to, subject, headers, idempotency key). An
    address in `sent.failing` raises instead."""
    box = _Sent()

    def fake(to, subject, text, html=None, *, headers=None, idempotency_key=None):
        if to in box.failing:
            raise EmailSendError("Resend rejected the send (HTTP 500)")
        box.append((to, subject, headers, idempotency_key))

    monkeypatch.setattr(outbox, "send_email", fake)
    return box


def _queue(db, to: str, **kw) -> uuid.UUID:
    outbox.enqueue(db, to=to, kind=kw.pop("kind", "test"), subject=kw.pop("subject", "Hello"),
                   text="Body", **kw)
    db.commit()
    row_id = db.scalar(select(EmailOutbox.id).where(EmailOutbox.to_email == to)
                       .order_by(EmailOutbox.created_at.desc()).limit(1))
    _to_front(db, row_id)
    return row_id


def _to_front(db, row_id) -> None:
    db.execute(update(EmailOutbox).where(EmailOutbox.id == row_id)
               .values(next_attempt_at=LONG_AGO))
    db.commit()


def _address() -> str:
    return f"mail_{uuid.uuid4().hex[:10]}@example.com"


def _me(client, headers) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["id"]


def _rows(user_id: str, kind: str | None = None) -> list[EmailOutbox]:
    with SessionLocal() as s:
        q = select(EmailOutbox).where(EmailOutbox.user_id == uuid.UUID(user_id))
        if kind:
            q = q.where(EmailOutbox.kind == kind)
        return list(s.scalars(q))


# --- the outbox -----------------------------------------------------------------

def test_a_queued_email_is_sent_once_with_its_id_as_the_idempotency_key(db, sent):
    to = _address()
    row_id = _queue(db, to, headers={"List-Unsubscribe": "<https://x.test/u>"})
    assert db.get(EmailOutbox, row_id).status == "pending"

    out = outbox.drain(db, limit=1)
    assert out["sent"] == 1
    assert sent == [(to, "Hello", {"List-Unsubscribe": "<https://x.test/u>"}, str(row_id))]
    db.expire_all()
    row = db.get(EmailOutbox, row_id)
    assert row.status == "sent" and row.sent_at is not None and row.attempts == 1

    # Sent rows are not sent again.
    outbox.drain(db, limit=5)
    assert [c for c in sent if c[0] == to] == [sent[0]]


def test_a_dedupe_key_queues_a_message_once(db):
    key = f"test:{uuid.uuid4().hex}"
    to = _address()
    assert outbox.enqueue(db, to=to, kind="t", subject="s", text="b", dedupe_key=key) is True
    assert outbox.enqueue(db, to=to, kind="t", subject="s", text="b", dedupe_key=key) is False
    db.commit()
    assert db.scalar(select(EmailOutbox.id).where(EmailOutbox.dedupe_key == key)) is not None
    assert len(db.scalars(select(EmailOutbox).where(EmailOutbox.to_email == to)).all()) == 1


def test_a_failing_send_backs_off_then_gives_up_after_five_tries(db, sent):
    to = _address()
    sent.failing.add(to)
    row_id = _queue(db, to)
    waits = []
    for attempt in range(1, outbox.MAX_ATTEMPTS + 1):
        now = datetime.now(UTC)
        out = outbox.drain(db, now=now, limit=1)
        db.expire_all()
        row = db.get(EmailOutbox, row_id)
        assert row.attempts == attempt
        assert row.last_error.startswith("EmailSendError")
        if attempt < outbox.MAX_ATTEMPTS:
            assert out["retried"] == 1 and row.status == "pending"
            waits.append(round((row.next_attempt_at - now).total_seconds() / 60))
            _to_front(db, row_id)
        else:
            assert out["failed"] == 1 and row.status == "failed"
    assert waits == [5, 10, 20, 40]
    assert sent == []


def test_settled_rows_older_than_thirty_days_are_purged(db, sent):
    old, recent, waiting = _address(), _address(), _address()
    ids = {}
    for to, status, age in ((old, "sent", 31), (recent, "sent", 29), (waiting, "pending", 40)):
        outbox.enqueue(db, to=to, kind="t", subject="s", text="b")
        db.flush()
        ids[to] = db.scalar(select(EmailOutbox.id).where(EmailOutbox.to_email == to))
        db.execute(update(EmailOutbox).where(EmailOutbox.id == ids[to]).values(
            status=status, created_at=datetime.now(UTC) - timedelta(days=age),
            next_attempt_at=datetime.now(UTC) + timedelta(days=1)))
    db.commit()
    assert outbox.drain(db, limit=0)["purged"] >= 1
    db.expire_all()
    assert db.get(EmailOutbox, ids[old]) is None
    assert db.get(EmailOutbox, ids[recent]) is not None
    assert db.get(EmailOutbox, ids[waiting]) is not None   # never sent: kept
    db.execute(update(EmailOutbox).where(EmailOutbox.id == ids[waiting]).values(status="skipped"))
    db.commit()


def test_resend_gets_the_headers_and_the_idempotency_key(monkeypatch):
    seen = {}

    def post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json)
        return httpx.Response(200, json={"id": "x"})

    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr(email_adapter.httpx, "post", post)
    email_adapter.send_email("a@example.com", "Subj", "Text", "<p>x</p>",
                             headers={"List-Unsubscribe": "<https://x.test/u>"},
                             idempotency_key="row-1")
    assert seen["headers"]["Idempotency-Key"] == "row-1"
    assert seen["headers"]["Authorization"] == "Bearer re_test"
    assert seen["json"]["headers"] == {"List-Unsubscribe": "<https://x.test/u>"}
    assert seen["json"]["to"] == ["a@example.com"] and seen["json"]["html"] == "<p>x</p>"

    # Without them, neither is sent.
    seen.clear()
    email_adapter.send_email("a@example.com", "Subj", "Text")
    assert "Idempotency-Key" not in seen["headers"] and "headers" not in seen["json"]


# --- store notices by email -----------------------------------------------------

def test_a_store_notice_is_emailed_only_while_email_is_on(client):
    store, owner, _ = _claimed_store(client)
    owner_id = _me(client, owner)
    _rate(client, store, 2.0)
    rows = _rows(owner_id, "notice:store_review_new")
    assert len(rows) == 1
    assert rows[0].subject == "New 2★ review" and rows[0].status == "pending"
    assert "unsubscribe" in rows[0].text_body.lower()

    # Email off: the notice still shows in the app, nothing more is queued.
    assert client.put(PREFS, headers=owner, json={"email": False}).status_code == 200
    _rate(client, store, 1.0)
    assert len(_rows(owner_id, "notice:store_review_new")) == 1
    kinds = [n["kind"] for n in client.get("/api/v1/notifications", headers=owner).json()]
    assert kinds.count("store_review_new") == 2

    # Email back on (a PUT sends every switch) but new reviews off: neither arrives.
    assert client.put(PREFS, headers=owner, json={"store_reviews": False}).status_code == 200
    _rate(client, store, 1.0)
    assert len(_rows(owner_id, "notice:store_review_new")) == 1


def test_only_store_notices_are_emailed_and_a_rollback_emails_nobody(db):
    user = make_user(db)
    db.commit()
    notify(db, user.id, "store_question_new", "New question", body="Do you ship?")
    db.rollback()
    assert _rows(str(user.id)) == []

    notify(db, user.id, "account_email_changed", "Your sign-in email changed")
    notify(db, user.id, "store_question_new", "New question", body="Do you ship?",
           link="/seller/abc/questions")
    db.commit()
    rows = _rows(str(user.id))
    assert [r.kind for r in rows] == ["notice:store_question_new"]
    assert rows[0].to_email == user.email and "Do you ship?" in rows[0].text_body


def test_the_email_escapes_what_members_wrote_and_links_only_over_https():
    subject, text, html = notification_email(
        title="New question", body="<script>alert(1)</script>",
        open_url="http://evil.test/x", settings_url="https://www.bluntly.ph/seller/dashboard",
        unsubscribe_url="https://www.bluntly.ph/unsubscribe?token=t")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "evil.test" not in html
    _, _, html = notification_email(
        title="New question", body=None, open_url="https://www.bluntly.ph/seller/x",
        settings_url="s", unsubscribe_url="u")
    assert 'href="https://www.bluntly.ph/seller/x"' in html


# --- one-click unsubscribe -------------------------------------------------------

def test_unsubscribe_tokens_are_signed_per_account_and_channel():
    uid = uuid.uuid4()
    token = outbox.unsubscribe_token(uid, "email")
    assert outbox.read_unsubscribe_token(token) == (uid, "email")
    raw_id, scope, sig = token.split(".")
    assert outbox.read_unsubscribe_token(f"{raw_id}.weekly_summary.{sig}") is None
    assert outbox.read_unsubscribe_token(f"{uuid.uuid4()}.email.{sig}") is None
    assert outbox.read_unsubscribe_token(f"{raw_id}.email.{'0' * 32}") is None
    assert outbox.read_unsubscribe_token(f"{raw_id}.everything.{sig}") is None
    assert outbox.read_unsubscribe_token("garbage") is None
    with pytest.raises(ValueError):
        outbox.unsubscribe_token(uid, "everything")


def test_list_unsubscribe_headers_only_for_an_https_site(monkeypatch):
    uid = uuid.uuid4()
    monkeypatch.setattr(settings, "site_url", "http://localhost:3000")
    assert outbox.unsubscribe_headers(uid, "email") == {}
    monkeypatch.setattr(settings, "site_url", "https://www.bluntly.ph")
    h = outbox.unsubscribe_headers(uid, "weekly_summary")
    assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert h["List-Unsubscribe"].startswith(
        "<https://www.bluntly.ph/api/v1/email/unsubscribe?token=")
    assert outbox.unsubscribe_page(uid, "email").startswith(
        "https://www.bluntly.ph/unsubscribe?token=")


def test_the_unsubscribe_link_reads_without_changing_and_posts_to_turn_off(client):
    uid, token, _ = register_and_token(client)
    me = {"Authorization": f"Bearer {token}"}
    link = outbox.unsubscribe_token(uuid.UUID(uid), "weekly_summary")
    url = f"/api/v1/email/unsubscribe?token={link}"

    got = client.get(url)
    assert got.status_code == 200 and got.json() == {"scope": "weekly_summary",
                                                     "subscribed": True}
    assert client.get(PREFS, headers=me).json()["weekly_summary"] is True   # a GET changes nothing

    # The RFC 8058 one-click POST, as a mail app sends it.
    off = client.post(url, content="List-Unsubscribe=One-Click",
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert off.status_code == 200 and off.json()["subscribed"] is False
    prefs = client.get(PREFS, headers=me).json()
    assert prefs["weekly_summary"] is False and prefs["email"] is True
    assert client.post(url).status_code == 200                       # again: still off
    assert client.get(url).json()["subscribed"] is False

    # Anything else is one 404 that says nothing about the account.
    for bad in (f"{uid}.weekly_summary.{'0' * 32}",
                outbox.unsubscribe_token(uuid.uuid4(), "email"), "x"):
        r = client.post(f"/api/v1/email/unsubscribe?token={bad}")
        assert r.status_code == 404 and r.json()["detail"] == "This unsubscribe link isn't valid."
    assert client.post("/api/v1/email/unsubscribe").status_code == 422


# --- the Monday summary -----------------------------------------------------------

def _weekly_rows(store_id: str) -> list[EmailOutbox]:
    with SessionLocal() as s:
        return list(s.scalars(select(EmailOutbox).where(
            EmailOutbox.kind == "weekly_summary",
            EmailOutbox.dedupe_key.like(f"weekly:{store_id}:%"))))


def test_a_store_week_counts_what_the_console_counts(client):
    store, owner, _ = _claimed_store(client)
    r1 = _rate(client, store, 5.0)
    _rate(client, store, 3.0)
    assert client.post(f"/api/v1/sellers/reviews/{r1}/response", headers=owner,
                       json={"body": "Thank you!"}).status_code == 200
    _, asker, _ = register_and_token(client)
    asker = {"Authorization": f"Bearer {asker}"}
    q1 = client.post("/api/v1/questions", headers=asker,
                     json={"seller_id": store, "body": "Do you restock?"}).json()
    client.post("/api/v1/questions", headers=asker, json={"seller_id": store, "body": "COD?"})
    assert client.post(f"/api/v1/questions/{q1['id']}/answers", headers=owner,
                       json={"body": "Every Monday."}).status_code == 201

    from app.models.seller import Seller
    with SessionLocal() as s:
        seller = s.get(Seller, uuid.UUID(store))
        week = weekly_summary_service.store_week(
            s, seller, since=datetime.now(UTC) - timedelta(days=7))
        assert week == {"rating": 4.0, "reviews_total": 2, "new_reviews": 2, "responses": 1,
                        "new_questions": 2, "reviews_waiting": 1, "questions_waiting": 1}
        # A week that starts after everything: nothing new, the waiting stays.
        later = weekly_summary_service.store_week(
            s, seller, since=datetime.now(UTC) + timedelta(minutes=1))
        assert later["new_reviews"] == later["responses"] == later["new_questions"] == 0
        assert later["reviews_waiting"] == 1 and later["questions_waiting"] == 1


def test_the_weekly_summary_is_queued_once_a_week_and_never_for_a_quiet_store(client):
    busy, busy_owner, _ = _claimed_store(client)
    _rate(client, busy, 2.0)
    quiet, _, _ = _claimed_store(client)
    off, off_owner, _ = _claimed_store(client)
    _rate(client, off, 2.0)
    assert client.put(PREFS, headers=off_owner, json={"weekly_summary": False}).status_code == 200

    with SessionLocal() as s:
        weekly_summary_service.enqueue_all(s)
    rows = _weekly_rows(busy)
    assert len(rows) == 1
    owner_email = client.get("/api/v1/auth/me", headers=busy_owner).json()["email"]
    assert rows[0].to_email == owner_email and rows[0].status == "pending"
    assert "Waiting on you: 1 review without your response." in rows[0].text_body
    assert "New reviews this week: 1" in rows[0].text_body
    assert _weekly_rows(quiet) == [] and _weekly_rows(off) == []

    # The job run twice in a week queues nothing twice.
    with SessionLocal() as s:
        weekly_summary_service.enqueue_all(s)
    assert len(_weekly_rows(busy)) == 1


def test_a_suspended_owner_gets_no_summary(client):
    store, owner, _ = _claimed_store(client)
    _rate(client, store, 2.0)
    owner_id = _me(client, owner)
    with SessionLocal() as s:
        s.get(User, uuid.UUID(owner_id)).is_suspended = True
        s.commit()
        weekly_summary_service.enqueue_all(s)
    assert _weekly_rows(store) == []
