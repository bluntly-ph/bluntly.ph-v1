"""PayMongo configuration (Figma Overlay/Settings/ConnectPayMongo 8237:25540).

What this does: a Super Admin saves the PayMongo keys, the payout methods to
offer (GCash, Maya, bank transfer) and test mode; the secret key is encrypted
at rest with INTEGRATION_SECRETS_KEY (Fernet) and never returned, only its last
four characters; "Test connection" makes one read-only call to PayMongo with
the saved key and records whether it was accepted.

What this does NOT do: send money. No payout, transfer or batch uses these
keys; payouts stay manual (Payouts → mark as sent). Turning automatic payouts
on is a separate owner decision and separate code.

Keys must match the mode: test mode takes pk_test_/sk_test_, live takes
pk_live_/sk_live_, so a live key is never saved by accident under "test".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.enums import ModerationAction
from app.models.moderation import ModerationLog
from app.models.triage import PlatformSetting
from app.models.user import User

KEY = "integration:paymongo"
METHODS = ("gcash", "maya", "bank")


@dataclass
class LastTest:
    ok: bool
    at: datetime
    detail: str


@dataclass
class PayMongoConfig:
    storage_ready: bool
    connected: bool
    test_mode: bool = True
    methods: list[str] = field(default_factory=list)
    public_key: str | None = None
    secret_hint: str | None = None
    connected_at: datetime | None = None
    last_test: LastTest | None = None
    #: Always False: saving keys never turns automatic payouts on.
    payouts_enabled: bool = False


def _fernet():
    if not settings.integration_secrets_key:
        return None
    from cryptography.fernet import Fernet
    try:
        return Fernet(settings.integration_secrets_key.encode())
    except (ValueError, TypeError):
        return None


def _row(db: Session) -> PlatformSetting | None:
    return db.get(PlatformSetting, KEY)


def read(db: Session) -> PayMongoConfig:
    row = _row(db)
    ready = _fernet() is not None
    if row is None:
        return PayMongoConfig(storage_ready=ready, connected=False)
    v = row.value or {}
    test = v.get("last_test")
    return PayMongoConfig(
        storage_ready=ready, connected=True, test_mode=bool(v.get("test_mode", True)),
        methods=[m for m in v.get("methods", []) if m in METHODS],
        public_key=v.get("public_key"), secret_hint=v.get("secret_hint"),
        connected_at=datetime.fromisoformat(v["connected_at"]) if v.get("connected_at") else None,
        last_test=LastTest(ok=bool(test["ok"]), at=datetime.fromisoformat(test["at"]),
                           detail=str(test.get("detail", ""))) if test else None)


def _invalid(message: str, code: str) -> AppError:
    return AppError(message, code=code, status_code=422, title="Invalid settings")


def save(db: Session, actor: User, *, public_key: str, secret_key: str | None,
         methods: list[str], test_mode: bool) -> PayMongoConfig:
    box = _fernet()
    if box is None:
        raise AppError("Keys can't be stored on this server yet: INTEGRATION_SECRETS_KEY is not "
                       "set.", code="secret_storage_unavailable", status_code=503,
                       title="Key storage unavailable")
    mode = "test" if test_mode else "live"
    public_key = public_key.strip()
    if not public_key.startswith(f"pk_{mode}_"):
        raise _invalid(f"In {mode} mode the public key starts with pk_{mode}_.", "public_key_mode")
    chosen = list(dict.fromkeys(m for m in methods if m in METHODS))
    if not chosen:
        raise _invalid("Choose at least one payout method.", "methods_required")
    row = _row(db)
    value = dict(row.value) if row else {}
    if secret_key:
        secret_key = secret_key.strip()
        if not secret_key.startswith(f"sk_{mode}_"):
            raise _invalid(f"In {mode} mode the secret key starts with sk_{mode}_.",
                           "secret_key_mode")
        value["secret_ciphertext"] = box.encrypt(secret_key.encode()).decode()
        value["secret_hint"] = f"sk_{mode}_…{secret_key[-4:]}"
        value.pop("last_test", None)
    elif not value.get("secret_ciphertext"):
        raise _invalid("Enter the secret key.", "secret_key_required")
    elif not str(value.get("secret_hint", "")).startswith(f"sk_{mode}_"):
        raise _invalid(f"The saved secret key isn't a {mode} key. Enter a {mode} secret key.",
                       "secret_key_mode")
    value.update(public_key=public_key, methods=chosen, test_mode=test_mode,
                 connected_at=value.get("connected_at") or datetime.now(UTC).isoformat())
    if row is None:
        row = PlatformSetting(key=KEY, value=value, updated_by=actor.id)
        db.add(row)
    else:
        row.value = value
        row.updated_by = actor.id
        row.updated_at = datetime.now(UTC)
    db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=actor.id,
                         action=ModerationAction.integration_change,
                         notes=f"PayMongo keys saved ({mode} mode)",
                         context={"integration": "paymongo", "mode": mode,
                                  "methods": chosen, "secret_changed": bool(secret_key)}))
    db.commit()
    return read(db)


def remove(db: Session, actor: User) -> PayMongoConfig:
    row = _row(db)
    if row is not None:
        db.delete(row)
        db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=actor.id,
                             action=ModerationAction.integration_change,
                             notes="PayMongo keys removed",
                             context={"integration": "paymongo", "event": "removed"}))
        db.commit()
    return read(db)


def _secret(db: Session) -> str | None:
    row, box = _row(db), _fernet()
    if row is None or box is None or not row.value.get("secret_ciphertext"):
        return None
    from cryptography.fernet import InvalidToken
    try:
        return box.decrypt(row.value["secret_ciphertext"].encode()).decode()
    except InvalidToken:
        return None


def test_connection(db: Session, actor: User, *, transport=None) -> PayMongoConfig:
    """One read-only call (list one payment) with the saved secret key: does
    PayMongo accept it? Records the result; sends nothing and moves nothing."""
    import httpx
    secret = _secret(db)
    if secret is None:
        raise AppError("Save the keys first.", code="not_connected", status_code=409,
                       title="Not connected")
    try:
        with httpx.Client(base_url=settings.paymongo_api_base, timeout=8.0,
                          transport=transport) as client:
            res = client.get("/v1/payments", params={"limit": 1}, auth=(secret, ""))
        if res.status_code == 200:
            ok, detail = True, "PayMongo accepted the key."
        elif res.status_code in (401, 403):
            ok, detail = False, "PayMongo refused the key."
        else:
            ok, detail = False, f"PayMongo answered {res.status_code}."
    except httpx.HTTPError:
        ok, detail = False, "Couldn't reach PayMongo from this server."
    row = _row(db)
    row.value = {**row.value, "last_test": {"ok": ok, "at": datetime.now(UTC).isoformat(),
                                            "detail": detail}}
    row.updated_at = datetime.now(UTC)
    db.commit()
    return read(db)
