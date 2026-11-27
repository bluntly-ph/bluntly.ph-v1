"""Seed the capstone-defense dataset through the real API.

Every workflow runs through the application's own endpoints, in process, so
validation, business rules and side effects (notifications, ledger entries,
aggregates, trust) are the real ones:

    register -> onboard -> submit a product -> moderator canonicalizes it and
    adds its image -> review with an uploaded photo -> moderator decides
    earnings (affiliate link / fund / reject) -> votes, comments, Q&A, Best
    Answer -> store reviews, a claim, owner responses, a suspected-fake flag ->
    price reports and their moderation -> clicks, a marketplace report import,
    remittances, cashouts -> reports, an investigation -> trust recomputed.

The database is written directly for only what no endpoint may do: roles,
back-dating (a real community is eight months old; an API call happens "now"),
and marking a payout paid on the manual rail's date.

Usage (after `python -m scripts.defense.reset --apply`, or with --reset):
    python -m scripts.defense.seed [--reset] [--out defense-seed.json]

Refuses anything but bluntly-ph-test or a local database. Images are fetched
from each manufacturer's own site and uploaded to TEST storage; on a local
database, where no storage is configured, products keep the placeholder.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import secrets
import sys
import time
import urllib.request
import uuid
from calendar import monthrange
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text

from scripts.defense import dataset as D
from scripts.defense.guard import require_defense_target

NOW = datetime.now(UTC)
_UA = "bluntly.ph/1.0 (+https://www.bluntly.ph)"
_IMAGE_CAP = 5 * 1024 * 1024


#: Column layouts of the marketplaces' own exports, as report_formats reads
#: them (tests/fixtures/*_report.csv are real exports with the same headers).
SHOPEE_HEADER = [
    "Order id", "Order Status", "Conversion id", "Order Time", "Complete Time", "Click Time",
    "Shop Name", "Shop id", "Shop Type", "Item id", "Item Name", "Model id", "Product Type",
    "Promotion id", "L1 Global Category", "L2 Global Category", "L3 Global Category",
    "Price(₱)", "Qty", "Offer Type", "Campaign Partner", "Purchase Value(₱)",
    "Refund Amount(₱)", "Item Shopee Commission Rate", "Item Shopee Commission(₱)",
    "Item Seller Commission Rate", "Item Seller Commission(₱)", "Item Total Commission(₱)",
    "Order Shopee Commission(₱)", "Order Seller Commission(₱)", "Total Order Commission(₱)",
    "Linked MCN Name", "MCN Contract id", "MCN Management Fee Rate", "MCN Management Fee(₱)",
    "Affiliate Agreement Fee Rate", "Affiliate Net Commission(₱)", "Affiliate Item Status",
    "Item Note", "Attribution Type", "Buyer Status", "Sub_id1", "Sub_id2", "Sub_id3",
    "Sub_id4", "Sub_id5", "Channel",
]
LAZADA_HEADER = [
    "Conversion Time", "Fulfilled Time", "Delivered Time", "Returned Time", "Offer ID",
    "Product ID", "Product Name", "Status", "Platform", "Country", "Check Out ID",
    "Sku Order ID", "Sub Order ID", "SKU", "SKU Name", "Category L1", "Brand ID", "Brand Name",
    "Seller ID", "Seller Name", "Commission Rate", "New User", "Payout", "Currency",
    "Aff Sub ID", "Validity", "Order Amount", "Adjustment", "Invite Id", "Invite Name",
    "DM offerId", "DM Start Time", "DM End Time", "DM Commission Rate", "DM Commission Fee",
    "Guided Type", "Is Code", "Attribution", "Payment Advice ID", "Payment Bill Period",
    "Payment Status", "Sub ID 1", "Sub ID 2", "Sub ID 3", "Sub ID 4", "Sub ID 5", "Sub ID 6",
]
_SHOPEE_NOTE = {
    "completed": "",
    "pending": "The status of the Item is pending, commissions will only be paid when "
               "it's completed",
    "cancelled": "The order was cancelled",
}


MANILA = ZoneInfo("Asia/Manila")


def _stamp_text(moment: datetime) -> str:
    return moment.astimezone(MANILA).strftime("%Y-%m-%d %H:%M:%S")


def _shopee_row(n: int, order, product: str, sub_id: str, clicked: datetime,
                rng: random.Random) -> tuple[dict, str, datetime | None]:
    """One item row of a Shopee affiliate commission report."""
    spec = D.PRODUCT[product]
    value = D.ORDER_VALUE[product]
    gross = Decimal(order.gross)
    status = order.status.title()
    ordered = clicked + timedelta(minutes=rng.randint(4, 40))
    completed = ordered + timedelta(days=3) if order.status == "completed" else None
    order_id = f"{ordered.astimezone(MANILA):%y%m%d}" + "".join(
        rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    conversion, item, model = (str(rng.randint(10**14, 10**15 - 1)),
                               str(rng.randint(10**10, 10**11 - 1)),
                               str(rng.randint(10**11, 10**12 - 1)))
    rate = f"{(gross / value * 100):.2f}%" if gross else "0.00%"
    row = {
        "Order id": order_id, "Order Status": status, "Conversion id": conversion,
        "Order Time": _stamp_text(ordered),
        "Complete Time": _stamp_text(completed) if completed else "",
        "Click Time": _stamp_text(clicked), "Shop Name": D.ORDER_SHOP[product],
        "Shop id": str(310000000 + n * 7919), "Shop Type": "Preferred", "Item id": item,
        "Item Name": f"{spec.brand} {spec.line}", "Model id": model,
        "Product Type": "Normal Product", "L1 Global Category": spec.category,
        "Price(₱)": str(value), "Qty": "1", "Offer Type": "Standard",
        "Purchase Value(₱)": str(value), "Item Shopee Commission Rate": rate,
        "Item Shopee Commission(₱)": order.gross, "Item Seller Commission Rate": "0.00%",
        "Item Seller Commission(₱)": "0", "Item Total Commission(₱)": order.gross,
        "Order Shopee Commission(₱)": order.gross, "Order Seller Commission(₱)": "0",
        "Total Order Commission(₱)": order.gross, "MCN Management Fee Rate": "0.00%",
        "MCN Management Fee(₱)": "0", "Affiliate Agreement Fee Rate": "100.00%",
        "Affiliate Net Commission(₱)": order.gross, "Affiliate Item Status": status,
        "Item Note": _SHOPEE_NOTE[order.status], "Attribution Type": "Ordered in Same Shop",
        "Buyer Status": rng.choice(("Existing", "New")), "Sub_id1": sub_id,
        "Channel": "Websites",
    }
    return row, "|".join((order_id, conversion, item, model, "")), completed


def _lazada_row(n: int, order, product: str, sub_id: str, clicked: datetime,
                rng: random.Random) -> tuple[dict, str, datetime | None]:
    """One row of a Lazada conversion report."""
    spec = D.PRODUCT[product]
    value = D.ORDER_VALUE[product]
    gross = Decimal(order.gross)
    status = {"completed": "Delivered", "pending": "Fulfilled",
              "cancelled": "Rejected"}[order.status]
    day = clicked.astimezone(MANILA).date()
    delivered = clicked + timedelta(days=5) if order.status == "completed" else None
    checkout = str(rng.randint(10**15, 10**16 - 1))
    sub_order = str(rng.randint(10**15, 10**16 - 1))
    product_id = str(rng.randint(10**9, 10**10 - 1))
    row = {
        "Conversion Time": f"{day}", "Fulfilled Time": f"{day + timedelta(days=2)}",
        "Delivered Time": f"{delivered.astimezone(MANILA).date()}" if delivered else "N/A",
        "Returned Time": "N/A", "Offer ID": f"NSKPH{rng.randint(10**9, 10**10 - 1)}",
        "Product ID": product_id, "Product Name": f"{spec.brand} {spec.line}",
        "Status": status, "Platform": "app", "Country": "PH", "Check Out ID": checkout,
        "Sku Order ID": checkout + str(n).zfill(4), "Sub Order ID": sub_order,
        "SKU": f"{product_id}_PH-{rng.randint(10**10, 10**11 - 1)}",
        "SKU Name": f"{spec.brand} {spec.line}", "Category L1": spec.category,
        "Brand ID": str(10000 + n), "Brand Name": spec.brand,
        "Seller ID": str(1000260000 + n), "Seller Name": D.ORDER_SHOP[product],
        "Commission Rate": f"{(gross / value):.4f}", "New User": "0", "Payout": order.gross,
        "Currency": "PHP", "Aff Sub ID": sub_id,
        "Validity": "invalid" if order.status == "cancelled" else "valid",
        "Order Amount": str(value), "Adjustment": "N/A", "Guided Type": "other_cps",
        "Is Code": "No", "Attribution": "Same Store", "Payment Advice ID": "-",
        "Payment Bill Period": "-", "Payment Status": "-",
    }
    return row, sub_order, delivered


class SeedError(RuntimeError):
    pass


def ago(days: float, *, hour: int | None = None) -> datetime:
    """A moment `days` before now, at a plausible hour of the day (Manila)."""
    moment = NOW - timedelta(days=days)
    if hour is not None:
        # 08:00-22:00 Manila is 00:00-14:00 UTC.
        moment = moment.replace(hour=(hour - 8) % 24, minute=(hour * 7) % 60, second=0,
                                microsecond=0)
    return min(moment, NOW - timedelta(minutes=5))


def email_for(person: D.Person, base: str) -> str:
    if person.login:
        local, domain = base.split("@", 1)
        return f"{local}+{person.key}@{domain}"
    return f"{person.username}@demo.bluntly.ph"


class Seeder:
    def __init__(self, kind: str, email_base: str, image_cache: Path | None):
        import logging

        from fastapi.testclient import TestClient

        from app.core.config import settings
        from app.main import app
        logging.getLogger("httpx").setLevel(logging.WARNING)
        # The seed is one client making hundreds of writes a minute; the
        # per-account and per-IP limits exist for people, and have their own tests.
        for name in dir(settings):
            if name.endswith("_rate_limit_max"):
                setattr(settings, name, 1_000_000)
        self.kind = kind
        self.settings = settings
        self.c = TestClient(app)
        self.email_base = email_base
        self.image_cache = image_cache
        self.storage = bool(settings.supabase_url and settings.supabase_secret_key) \
            and kind == "test"
        self.uid: dict[str, str] = {}
        self.token: dict[str, str] = {}
        self.product: dict[str, str] = {}
        self.store: dict[str, str] = {}
        self.review: dict[str, str] = {}
        self.question: dict[str, str] = {}
        self.store_review: dict[str, str] = {}
        self.image_bytes: dict[str, bytes] = {}
        self.log: list[str] = []

    # ------------------------------------------------------------ plumbing

    def h(self, who: str | None) -> dict:
        return {"Authorization": f"Bearer {self.token[who]}"} if who else {}

    def call(self, method: str, path: str, who: str | None = None,
             expect: tuple[int, ...] = (200, 201, 202, 204), **kw):
        r = self.c.request(method, path, headers=self.h(who), **kw)
        if r.status_code not in expect:
            raise SeedError(f"{method} {path} as {who}: HTTP {r.status_code} {r.text[:600]}")
        if r.status_code == 204 or not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    def db(self):
        from app.db.session import SessionLocal
        return SessionLocal()

    def stamp(self, table: str, row_id: str, **fields) -> None:
        """Back-date a row. Direct SQL: no endpoint may rewrite history."""
        from sqlalchemy import text

        sets = ", ".join(f"{k} = :{k}" for k in fields)
        db = self.db()
        try:
            db.execute(text(f"UPDATE {table} SET {sets} WHERE id = :id"),
                       {**fields, "id": row_id})
            db.commit()
        finally:
            db.close()

    def note(self, message: str) -> None:
        self.log.append(message)
        print(f"  - {message}", flush=True)

    # ------------------------------------------------------------ people

    def people(self) -> None:
        from app.core.security import create_access_token
        from app.models.enums import MemberRole
        from app.models.user import User

        for person in (*D.PERSONAS, *D.COMMUNITY):
            email = email_for(person, self.email_base)
            db = self.db()
            try:
                from sqlalchemy import func, select
                existing = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
                uid = str(existing.id) if existing else None
            finally:
                db.close()
            if uid is None:
                # A random password nobody records: every account signs in by
                # an emailed one-time code, as the site's own login does.
                body = self.call("POST", "/api/v1/auth/register",
                                 json={"email": email, "password": secrets.token_urlsafe(24)})
                uid = body["user"]["id"]
            self.uid[person.key] = uid
            # The role is set before the token is minted so it carries it.
            joined = ago(person.joined_days_ago, hour=19)
            db = self.db()
            try:
                user = db.get(User, uuid.UUID(uid))
                user.role = MemberRole(person.role)
                user.created_at = joined
                db.commit()
            finally:
                db.close()
            self.token[person.key] = create_access_token(uuid.UUID(uid), person.role)
            # Onboarding, as the /onboarding page does it.
            self.call("PATCH", "/api/v1/users/me", person.key, json={
                "username": person.username, "display_name": person.display_name,
                "interests": list(person.interests)})
        self.note(f"{len(self.uid)} accounts ({len(D.PERSONAS)} personas)")

    # ------------------------------------------------------------ images

    def fetch_image(self, spec: D.ProductSpec) -> bytes | None:
        if spec.key in self.image_bytes:
            return self.image_bytes[spec.key]
        cached = self.image_cache / f"{spec.key}.img" if self.image_cache else None
        if cached and cached.exists():
            data = cached.read_bytes()
        else:
            data = None
            for attempt in range(3):
                try:
                    req = urllib.request.Request(spec.image_url, headers={"User-Agent": _UA})
                    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                        data = resp.read(_IMAGE_CAP + 1)
                    break
                except Exception as exc:  # noqa: BLE001 - reported, retried
                    print(f"    image {spec.key}: {exc} (attempt {attempt + 1})", flush=True)
                    time.sleep(2 * (attempt + 1))
            if data and cached:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(data)
        from app.services.storage import sniff_image_type
        if not data or len(data) > _IMAGE_CAP or sniff_image_type(data) is None:
            print(f"    image {spec.key}: unusable", flush=True)
            return None
        self.image_bytes[spec.key] = data
        return data

    def review_photo(self, author: str, product_key: str) -> str:
        """The author uploads their product photo, as the composer does."""
        if self.storage:
            data = self.fetch_image(D.PRODUCT[product_key])
            if data:
                from app.services.storage import sniff_image_type
                mime = sniff_image_type(data)
                ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
                body = self.call("POST", "/api/v1/reviews/photo", author,
                                 files={"file": (f"{product_key}.{ext}", data, mime)})
                return body["url"]
        # Local database: no storage to upload to. The URL still has to be one
        # the author owns, because verification is derived from it. It names
        # the product, so a rehearsal browser can serve the cached picture for
        # it (e2e/defense-walkthrough.spec.ts); nothing else reads that part.
        from app.services.storage import REVIEW_BUCKET
        base = (self.settings.supabase_url or "https://local.supabase.co").rstrip("/")
        return (f"{base}/storage/v1/object/public/{REVIEW_BUCKET}/"
                f"{self.uid[author]}/{product_key}-{uuid.uuid4().hex}.jpg")

    # ------------------------------------------------------------ catalogue

    def products(self) -> None:
        for spec in D.PRODUCTS:
            source = spec.shopee_url or spec.lazada_url
            body = self.call("POST", "/api/v1/products", spec.submitter, json={
                "name": spec.submitted_name, "category": spec.category,
                "source_url": source})
            pid = body["id"]
            self.product[spec.key] = pid
            self.call("POST", f"/api/v1/products/{pid}/canonicalize", "administrator", json={
                "brand": spec.brand, "product_line": spec.line, "key_spec": spec.key_spec,
                "descriptor": spec.descriptor, "category": spec.category,
                "aliases": list(spec.aliases)})
            if not self.storage and self.image_cache:
                self.fetch_image(spec)  # cached for the rehearsal browser
            if self.storage:
                data = self.fetch_image(spec)
                if data:
                    from app.services.storage import sniff_image_type
                    mime = sniff_image_type(data)
                    self.call("POST", f"/api/v1/products/{pid}/image", "administrator",
                              files={"file": (f"{spec.key}", data, mime)})
            submitted = ago(D.PEOPLE[spec.submitter].joined_days_ago - 3)
            first_review = max((r.days_ago for r in D.REVIEWS if r.product == spec.key),
                               default=30)
            submitted = min(submitted, ago(first_review + 1))
            self.stamp("products", pid, created_at=submitted, updated_at=submitted)
        for key, who, name, category in D.PENDING_SUBMISSIONS:
            body = self.call("POST", "/api/v1/products", who,
                             json={"name": name, "category": category})
            self.product[key] = body["id"]
            self.stamp("products", body["id"], created_at=ago(2), updated_at=ago(2))
        self.note(f"{len(D.PRODUCTS)} products canonicalized"
                  f"{' with images' if self.storage else ' (no storage: placeholders)'}, "
                  f"{len(D.PENDING_SUBMISSIONS)} submissions pending")

    def stores(self) -> None:
        for spec in D.STORES:
            body = self.call("POST", "/api/v1/sellers", spec.added_by, json={
                "display_name": spec.name, "platform": spec.platform})
            sid = body["id"]
            self.store[spec.key] = sid
            added = ago(D.PEOPLE[spec.added_by].joined_days_ago - 5)
            self.stamp("sellers", sid, created_at=added, updated_at=added)
            if spec.claim:
                claim = self.call("POST", f"/api/v1/sellers/{sid}/claims", spec.owner, json={
                    "registration_kind": "dti",
                    "registration_number": spec.registration_number,
                    "registered_business_name": spec.registered_business_name,
                    "marketplace_shop_name": spec.name,
                    "evidence": "Store owner since 2023. The DTI certificate matches the shop "
                                "name on the marketplace listing."})
                filed = ago(D.PEOPLE[spec.owner].joined_days_ago - 2)
                self.stamp("seller_claims", claim["id"], created_at=filed)
                if spec.claim == "approved":
                    self.call("POST", f"/api/v1/admin/seller-claims/{claim['id']}/decision",
                              "administrator", json={"decision": "approve",
                                                 "note": "DTI registration matches the shop."})
                    self.stamp("seller_claims", claim["id"], decided_at=filed + timedelta(days=1))
        self.note(f"{len(D.STORES)} stores (1 claimed, 1 claim pending)")

    # ------------------------------------------------------------ reviews

    def reviews(self) -> None:
        for spec in sorted(D.REVIEWS, key=lambda r: -r.days_ago):
            pid = self.product[spec.product]
            body = {
                "product_id": pid, "title": spec.title, "discussion": spec.discussion,
                "verdict": spec.verdict, "verdict_explanation": spec.explanation,
                "target_audience": spec.target, "anti_target_audience": spec.anti,
                "star_rating": spec.stars, "pros": list(spec.pros), "cons": list(spec.cons),
                "material_relationship": "none",
            }
            if spec.price:
                body["price_paid"] = spec.price
                body["price_platform"] = spec.platform
            if spec.photo:
                body["photo_url"] = self.review_photo(spec.author, spec.product)
            created = self.call("POST", "/api/v1/reviews", spec.author, json=body)
            rid = created["id"]
            self.review[spec.key] = rid
            when = ago(spec.days_ago, hour=20)
            self.stamp("reviews", rid, created_at=when, updated_at=when, published_at=when)
        self.note(f"{len(D.REVIEWS)} reviews published")

    def decisions(self) -> None:
        counts: dict[str, int] = defaultdict(int)
        for spec in D.REVIEWS:
            if spec.decision in (None, "pending"):
                counts[spec.decision or "unverified"] += 1
                continue
            rid = self.review[spec.key]
            if spec.decision == "monetized":
                product = D.PRODUCT[spec.product]
                url = product.shopee_url or product.lazada_url
                platform = "shopee" if product.shopee_url else "lazada"
                if not url:
                    raise SeedError(f"{spec.key}: monetized without a real link")
                self.call("POST", f"/api/v1/admin/reviews/{rid}/referral-link", "administrator",
                          json={"url": url, "platform": platform,
                                "sub_id": f"blt{spec.key.replace('_', '')}"[:40]})
            elif spec.decision in ("approved", "honesty_fund"):
                self.call("POST", f"/api/v1/admin/reviews/{rid}/approve-earnings", "administrator")
            elif spec.decision == "rejected":
                self.call("POST", f"/api/v1/admin/reviews/{rid}/reject", "administrator",
                          json={"reason": spec.reject_reason})
            counts[spec.decision] += 1
        self.note("earnings decisions: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))

    def updates_and_deletes(self) -> None:
        for spec in D.REVIEWS:
            if spec.update:
                u = spec.update
                entry = self.call("POST", f"/api/v1/reviews/{self.review[spec.key]}/updates",
                                  spec.author, json={
                                      "title": u.title, "discussion": u.discussion,
                                      "verdict": u.verdict, "star_rating": u.stars,
                                      "pros": list(u.pros), "cons": list(u.cons),
                                      "material_relationship": "none"})
                when = ago(u.days_ago, hour=21)
                self.stamp("reviews", entry["id"], created_at=when, updated_at=when,
                           published_at=when)
                self.note(f"thread update on {spec.key}")
            if spec.author_deletes:
                self.call("DELETE", f"/api/v1/reviews/{self.review[spec.key]}", spec.author,
                          params={"confirm": "delete-thread"})
                self.note(f"{spec.key} removed by its author")

    # ------------------------------------------------------------ community

    def _voter_pool(self) -> list[str]:
        excluded = {"rico", "administrator", "superadmin", "jomar"}
        return sorted(k for k in D.PEOPLE if k not in excluded)

    def votes(self) -> None:
        pool = self._voter_pool()
        per_author: dict[tuple[str, str], int] = defaultdict(int)
        cast = 0
        for spec in D.REVIEWS:
            if spec.author_deletes or spec.decision == "pending":
                continue
            rid = self.review[spec.key]
            rng = random.Random(f"votes:{spec.key}")
            if spec.author == "jomar":
                # The ring votes on everything; three strangers each vote once.
                others = [k for k in pool if k not in D.RING and k != "paolo"]
                idx = [r.key for r in D.REVIEWS if r.author == "jomar"].index(spec.key)
                ups = list(D.RING) + others[idx * 3: idx * 3 + 3]
                downs: list[str] = []
            else:
                candidates = [k for k in pool if k != spec.author
                              and per_author[(k, spec.author)] < 3]
                rng.shuffle(candidates)
                ups = candidates[:spec.ups]
                downs = candidates[spec.ups: spec.ups + spec.downs]
            for voter, direction in [(v, "up") for v in ups] + [(v, "down") for v in downs]:
                vote = self.call("POST", f"/api/v1/reviews/{rid}/vote", voter,
                                 json={"vote": direction})
                per_author[(voter, spec.author)] += 1
                window = max(1, min(25, spec.days_ago - 1))
                when = ago(spec.days_ago - rng.uniform(0.2, window), hour=rng.randint(9, 22))
                vote_id = (vote or {}).get("id")
                if vote_id:
                    self.stamp("review_votes", vote_id, created_at=when, updated_at=when)
                else:
                    self._stamp_vote(rid, voter, when)
                cast += 1
        # The ring's other half: Jomar up-votes one review by each ring member,
        # the reciprocity the collusion check measures (dev/QA sync 2026-09-29).
        for member in D.RING:
            spec = next(r for r in D.REVIEWS if r.author == member and not r.author_deletes
                        and r.decision != "pending")
            rid = self.review[spec.key]
            vote = self.call("POST", f"/api/v1/reviews/{rid}/vote", "jomar",
                             json={"vote": "up"}, expect=(200, 201, 409))
            when = ago(max(1, spec.days_ago - 2), hour=21)
            vote_id = (vote or {}).get("id")
            if vote_id:
                self.stamp("review_votes", vote_id, created_at=when, updated_at=when)
            cast += 1
        self.note(f"{cast} helpfulness votes")

    def gate_votes(self) -> None:
        """Readers find the queued reviews helpful until the real gate admits them.

        Post-Seeding (the owner's rule, 2026-09-22): a review enters the
        moderator's earnings queue only when its trust-weighted up-votes pass
        the Wilson threshold with three Stage 2+ voters. Each vote carries its
        voter's weight at the moment it is cast, so this runs after trust has
        settled once, strongest voters first, and stops as soon as the review
        is queued - no more votes than the rule needs.
        """
        from sqlalchemy import select

        from app.models.review import Review
        from app.models.user import User

        self._recompute_trust()
        db = self.db()
        try:
            weights = {k: (u.trust_stage, float(u.reputation_score or 0))
                       for k, u in ((k, db.get(User, uuid.UUID(v))) for k, v in self.uid.items())}
        finally:
            db.close()
        pool = sorted((k for k in self._voter_pool() if weights[k][0] >= 2),
                      key=lambda k: (-weights[k][0], -weights[k][1], k))
        for spec in D.REVIEWS:
            if spec.decision != "pending":
                continue
            rid = self.review[spec.key]
            rng = random.Random(f"gate:{spec.key}")
            cast = 0
            for voter in (k for k in pool if k != spec.author):
                self.call("POST", f"/api/v1/reviews/{rid}/vote", voter, json={"vote": "up"})
                cast += 1
                window = max(1, min(20, spec.days_ago - 1))
                self._stamp_vote(rid, voter, ago(spec.days_ago - rng.uniform(0.2, window),
                                                 hour=rng.randint(9, 22)))
                db = self.db()
                try:
                    status = db.scalar(select(Review.earn_eligible_status)
                                       .where(Review.id == uuid.UUID(rid)))
                finally:
                    db.close()
                if status is not None and status.value == "pending":
                    break
            else:
                raise SeedError(f"{spec.key}: the gate never admitted it ({cast} votes)")
            self.note(f"{spec.key} entered the earnings queue after {cast} helpful votes")

    def _recompute_trust(self) -> None:
        from app.services.trust_service import recompute_user_trust

        db = self.db()
        try:
            for _ in range(2):
                for uid in self.uid.values():
                    recompute_user_trust(db, uuid.UUID(uid))
                db.commit()
        finally:
            db.close()

    def _stamp_vote(self, review_id: str, voter: str, when: datetime) -> None:
        from sqlalchemy import text
        db = self.db()
        try:
            db.execute(text("UPDATE review_votes SET created_at = :w, updated_at = :w "
                            "WHERE review_id = :r AND voter_id = :v"),
                       {"w": when, "r": review_id, "v": self.uid[voter]})
            db.commit()
        finally:
            db.close()

    def comments(self) -> None:
        made = 0

        def post(review_key: str, spec: D.CommentSpec, parent: str | None) -> None:
            nonlocal made
            rid = self.review[review_key]
            body = {"body": spec.body}
            if parent:
                body["parent_id"] = parent
            c = self.call("POST", f"/api/v1/reviews/{rid}/comments", spec.author, json=body)
            review = D.REVIEW[review_key]
            when = ago(max(0.05, review.days_ago - spec.after_days - made % 3 * 0.01),
                       hour=12 + made % 9)
            self.stamp("review_comments", c["id"], created_at=when, updated_at=when)
            made += 1
            for liker in spec.liked_by:
                self.call("POST", f"/api/v1/comments/{c['id']}/vote", liker, json={"vote": "up"})
            for reply in spec.replies:
                post(review_key, reply, c["id"])

        for review_key, threads in D.COMMENTS.items():
            for spec in threads:
                post(review_key, spec, None)
        self.note(f"{made} comments and replies")

    def questions(self) -> None:
        answered = 0
        for spec in D.QUESTIONS:
            body = {"body": spec.body, "directed_to": spec.directed_to}
            if spec.product:
                body["product_id"] = self.product[spec.product]
            if spec.store:
                body["seller_id"] = self.store[spec.store]
            q = self.call("POST", "/api/v1/questions", spec.asker, json=body)
            qid = q["id"]
            self.question[spec.key] = qid
            asked = ago(spec.days_ago, hour=10)
            self.stamp("questions", qid, created_at=asked, updated_at=asked)
            for who in spec.subscribers:
                self.call("PUT", f"/api/v1/questions/{qid}/subscription", who,
                          json={"subscribed": True})
            answer_ids = []
            for n, a in enumerate(spec.answers):
                body = {"body": a.body}
                if (spec.key, n) in D.ANSWER_RATINGS:
                    body["rating"] = D.ANSWER_RATINGS[(spec.key, n)]
                ans = self.call("POST", f"/api/v1/questions/{qid}/answers", a.author, json=body)
                when = min(ago(spec.days_ago - a.after_days, hour=14), NOW - timedelta(hours=1))
                self.stamp("answers", ans["id"], created_at=when, updated_at=when)
                answer_ids.append(ans["id"])
                answered += 1
            if spec.best is not None:
                self.call("POST", f"/api/v1/questions/{qid}/answers/{answer_ids[spec.best]}/best",
                          spec.asker)
        self.note(f"{len(D.QUESTIONS)} questions, {answered} answers")

    def store_reviews(self) -> None:
        for spec in D.STORE_REVIEWS:
            sid = self.store[spec.store]
            body = {
                "accuracy": spec.accuracy, "order_completeness": spec.complete,
                "customer_service": spec.service, "packaging_quality": spec.packaging,
                "overall_rating": spec.overall, "would_recommend": spec.recommend,
                "title": spec.title, "comment": spec.comment, "order_id": spec.order_id,
            }
            if spec.product:
                body["product_id"] = self.product[spec.product]
            sr = self.call("POST", f"/api/v1/sellers/{sid}/reviews", spec.author, json=body)
            self.store_review[spec.key] = sr["id"]
            when = ago(spec.days_ago, hour=18)
            self.stamp("seller_reviews", sr["id"], created_at=when, updated_at=when)
            owner = next((s.owner for s in D.STORES if s.key == spec.store
                          and s.claim == "approved"), None)
            if spec.response and owner:
                self.call("POST", f"/api/v1/sellers/reviews/{sr['id']}/response", owner,
                          json={"body": spec.response})
                self.stamp("seller_reviews", sr["id"],
                           seller_response_at=min(when + timedelta(days=1), NOW))
            if spec.appeal and owner:
                appeal = self.call("POST", f"/api/v1/sellers/reviews/{sr['id']}/appeal", owner,
                                   json={"reason": spec.appeal})
                self.call("POST", f"/api/v1/admin/seller-review-appeals/{appeal['id']}"
                                  "/substantiation-request", "administrator", json={
                                      "note": "The store says it has no record of this order. "
                                              "Please upload your order confirmation or a "
                                              "photo of the parcel's shipping label."})
        self.note(f"{len(D.STORE_REVIEWS)} store reviews, owner responses and a fake-review flag")

    # ------------------------------------------------------------ prices

    def prices(self) -> None:
        from sqlalchemy import text

        # The prices reviewers entered with their reviews: dated with the
        # review, then approved oldest first, as a moderator works the queue.
        by_review = {rid: key for key, rid in self.review.items()}
        db = self.db()
        try:
            rows = db.execute(text(
                "SELECT id::text, review_id::text FROM price_history "
                "WHERE source = 'review' AND status = 'pending'")).all()
        finally:
            db.close()
        dated = []
        for obs_id, review_id in rows:
            key = by_review.get(review_id)
            if key is None:
                continue
            spec = D.REVIEW[key]
            day = ago(spec.days_ago)
            self.stamp("price_history", obs_id, observed_at=day.date(), created_at=day)
            dated.append((spec.days_ago, obs_id))
        approved = 0
        for _, obs_id in sorted(dated, reverse=True):
            self._approve_price(obs_id)
            approved += 1
        held = 0
        for spec in sorted(D.PRICES, key=lambda p: -p.days_ago):
            pid = self.product[spec.product]
            body = {"platform": spec.platform, "price": spec.price,
                    "observed_at": ago(spec.days_ago).date().isoformat()}
            if spec.variant:
                body["variant"] = spec.variant
            own = next(r.key for r in D.REVIEWS
                       if r.author == spec.submitter and r.product == spec.product)
            body["review_id"] = self.review[own]
            obs = self.call("POST", f"/api/v1/products/{pid}/prices", spec.submitter, json=body)
            self.stamp("price_history", obs["id"], created_at=ago(spec.days_ago, hour=16))
            if obs.get("status") == "pending":
                if spec.decision == "approve":
                    self._approve_price(obs["id"])
                else:
                    held += 1
                    continue
            approved += 1
        self.note(f"{approved} prices published, {held} waiting for a moderator "
                  "(one outlier, one without a baseline)")

    def _approve_price(self, obs_id: str) -> None:
        self.call("POST", f"/api/v1/admin/price-observations/{obs_id}/decision", "administrator",
                  json={"decision": "approve"})

    # ------------------------------------------------------------ money

    def money(self) -> None:
        from sqlalchemy import select

        from app.models.session import Session as ClickSession

        for who, account in D.PAYOUT_ACCOUNTS.items():
            self.call("PATCH", "/api/v1/auth/me/payout-account", who,
                      json={"payout_account": account})
        rng = random.Random("orders")
        exports: dict[str, list[dict]] = {"shopee": [], "lazada": []}
        imported_on: dict[str, datetime] = {}
        for n, order in enumerate(D.ORDERS, start=1):
            rid = self.review[order.review]
            # The reader's click through the review's link, as the site records it.
            r = self.c.get(f"/r/{rid}", follow_redirects=False)
            if r.status_code != 302:
                raise SeedError(f"/r/{rid}: {r.status_code}")
            clicked = ago(order.days_ago, hour=21) + timedelta(minutes=rng.randint(0, 50))
            db = self.db()
            try:
                session = db.scalars(select(ClickSession).where(
                    ClickSession.review_id == uuid.UUID(rid))
                    .order_by(ClickSession.created_at.desc())).first()
                session.clicked_at = clicked
                session.created_at = clicked
                db.commit()
                sub_id = db.scalar(text("SELECT sub_id FROM referral_links WHERE review_id = :r "
                                        "AND status = 'active'"), {"r": rid})
            finally:
                db.close()
            product = D.REVIEW[order.review].product
            platform = "shopee" if D.PRODUCT[product].shopee_url else "lazada"
            row, identity, final = (_shopee_row if platform == "shopee" else _lazada_row)(
                n, order, product, sub_id, clicked, rng)
            exports[platform].append(row)
            # The moderator imports a finished month's report a few days later.
            imported_on[identity] = (final or clicked) + timedelta(days=2, hours=3)
        results = []
        for platform, rows in exports.items():
            header = SHOPEE_HEADER if platform == "shopee" else LAZADA_HEADER
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=header, restval="")
            w.writeheader()
            w.writerows(rows)
            name = ("shopee-affiliate-commission-report.csv" if platform == "shopee"
                    else "lazada-conversion-report.csv")
            data = buf.getvalue().encode("utf-8-sig")
            preview = self.call("POST", "/api/v1/admin/affiliate/preview", "administrator",
                                files={"file": (name, data, "text/csv")})
            result = self.call("POST", "/api/v1/admin/affiliate/import", "administrator",
                               files={"file": (name, data, "text/csv")})
            if result["recognised"] != preview["recognised"]:
                raise SeedError(f"{platform} import did not do what its preview said")
            results.append(f"{platform}: {result['total_rows']} rows, "
                           f"{result['recognised']} paid, {result['lifecycle']}")
        self.note("affiliate reports imported - " + "; ".join(results))
        self._backdate_commissions(imported_on)
        remitted = self._remit()
        self.note(f"remittances recorded for {remitted}")
        for spec in D.CASHOUTS:
            payout = self.call("POST", "/api/v1/payouts/cashout", spec.person,
                               json={"amount": spec.amount})
            pid = payout["id"]
            when = ago(spec.days_ago, hour=11)
            if spec.outcome == "paid":
                self.call("POST", f"/api/v1/admin/payouts/{pid}/mark-paid", "administrator",
                          json={"provider_ref": "PAYPAL-SANDBOX-8K2Q4471"})
                self.stamp("payouts", pid, created_at=when, updated_at=when + timedelta(days=2),
                           paid_at=when + timedelta(days=2))
            else:
                self.stamp("payouts", pid, created_at=when, updated_at=when)
        self.note("cashouts: one paid, one requested")

    def _backdate_commissions(self, imported_on: dict[str, datetime]) -> None:
        """Each commission and ledger row dates from its report's import."""
        db = self.db()
        try:
            for identity, when in imported_on.items():
                db.execute(text("UPDATE commissions SET created_at = :w, updated_at = :w "
                                "WHERE row_reference = :i"), {"w": when, "i": identity})
                db.execute(text("UPDATE affiliate_postbacks SET received_at = :w "
                                "WHERE external_sub_order_id = :i"), {"w": when, "i": identity})
            db.commit()
        finally:
            db.close()

    def _remit(self) -> list[str]:
        """Record the marketplace's payout for every month that ended 30+ days ago."""
        from sqlalchemy import text
        db = self.db()
        try:
            rows = db.execute(text("""
                SELECT platform::text, cycle_month, sum(gross_amount)
                  FROM commissions WHERE cleared_at IS NULL AND platform IS NOT NULL
                 GROUP BY 1, 2 ORDER BY 2
            """)).all()
        finally:
            db.close()
        done = []
        for platform, cycle, gross in rows:
            last_day = date(cycle.year, cycle.month, monthrange(cycle.year, cycle.month)[1])
            if (NOW.date() - last_day).days < 30:
                continue
            received = last_day + timedelta(days=22)
            self.call("POST", "/api/v1/admin/remittances", "administrator", json={
                "platform": platform, "cycle_month": cycle.isoformat(),
                "amount_received": str(gross), "received_on": received.isoformat(),
                "reference": f"{platform.upper()}-PAYOUT-{cycle:%Y%m}"})
            done.append(f"{platform} {cycle:%b %Y}")
        return done

    # ------------------------------------------------------------ moderation

    def moderation(self) -> None:
        for spec in D.REPORTS:
            rid = self.review[spec.review]
            self.call("POST", f"/api/v1/reviews/{rid}/report", spec.reporter,
                      json={"reason": spec.reason, "notes": spec.notes})
        queue = self.call("GET", "/api/v1/admin/reports", "administrator") or []
        items = queue if isinstance(queue, list) else queue.get("items", [])
        for spec in D.REPORTS:
            if not spec.resolution:
                continue
            rid = self.review[spec.review]
            report = next((i["report"] for i in items
                           if str(i["report"].get("target_ref")) == rid), None)
            if report is None:
                raise SeedError(f"report on {spec.review} not in the queue")
            self.call("POST", f"/api/v1/admin/reports/{report['id']}/decision", "administrator",
                      json={"resolution": spec.resolution, "notes": spec.resolution_notes})
        for who, note in D.INVESTIGATIONS.items():
            self.call("PUT", f"/api/v1/admin/users/{self.uid[who]}/investigation", "administrator",
                      json={"under_investigation": True, "note": note})
        self.note(f"{len(D.REPORTS)} reports ({sum(1 for r in D.REPORTS if r.resolution)} "
                  f"resolved), {len(D.INVESTIGATIONS)} investigation")

    def integrity(self) -> None:
        """The scheduled integrity sweep, run once: automated signals filed into
        the same report queue, labelled SYSTEM_DETECTED, with their evidence
        (Business Rules §12). Jomar's recent PS5 review trips the copied-text
        and collusion checks here, from the real checks."""
        result = self.call("POST", "/api/v1/admin/integrity/sweep", "administrator") or {}
        self.note(f"integrity sweep: {result.get('evaluated', 0)} reviews checked, "
                  f"{result.get('filed', 0)} system reports filed")

    def requests(self) -> None:
        """The Bounty Board (dev/QA sync 2026-09-29): every request names its
        product; every review of it written after the request is an answer; the
        asker picks the Best Answer, and the request leaves the board but keeps
        its page. Answers already exist in the story, so each asker's
        "Someone answered your request" notice is written by the platform's own
        notification service and dated to the answer it announces."""
        from sqlalchemy import text

        from app.models.request_board import ReviewRequest
        from app.models.review import Review
        from app.services import notification_service, request_service

        picked = 0
        for spec in D.REQUESTS:
            req = self.call("POST", "/api/v1/requests", spec.requester,
                            json={"title": spec.title, "details": spec.details,
                                  "product_id": self.product[spec.product]})
            when = ago(spec.days_ago, hour=15)
            self.stamp("review_requests", req["id"], created_at=when, updated_at=when)
            for who in spec.upvoters:
                self.call("POST", f"/api/v1/requests/{req['id']}/upvote", who)
            db = self.db()
            try:
                row = db.get(ReviewRequest, uuid.UUID(req["id"]))
                for review in request_service.answers(db, row):
                    notification_service.request_answered(db, row, review)
                    db.flush()
                    db.execute(text(
                        "UPDATE notifications SET created_at = :at WHERE kind = "
                        "'request_answered' AND link = :link AND created_at > :at"),
                        {"at": review.created_at, "link": f"/requests/{row.id}"})
                db.commit()
            finally:
                db.close()
            if spec.best_answer:
                rid = self.review[spec.best_answer]
                self.call("POST", f"/api/v1/requests/{req['id']}/best-answer", spec.requester,
                          json={"review_id": rid})
                db = self.db()
                try:
                    answered = db.get(Review, uuid.UUID(rid)).created_at + timedelta(days=2)
                finally:
                    db.close()
                self.stamp("review_requests", req["id"], fulfilled_at=answered,
                           updated_at=answered)
                picked += 1
        self.note(f"{len(D.REQUESTS)} review requests ({picked} with a Best Answer)")

    def traffic(self) -> None:
        """Readers opening reviews, recorded by the service the site's proxy feeds.

        The live site learns a view from a beacon its proxy posts for each review
        page request (routes/traffic_ingest.py). Here the same service is called
        directly, back-dated across each review's life: attention front-loaded
        after publication, never quite stopping, and some of it this week, so
        the dashboard and the affiliate queue's momentum have something to read.
        Views are "times opened", never readers - nothing identifies anyone.
        """
        from sqlalchemy import text

        from app.services import request_traffic_service as traffic
        from app.services.request_geo import RequestGeo

        rng = random.Random("traffic")
        cities = [RequestGeo(country="PH", region=region, city=city, latitude=lat,
                             longitude=lon)
                  for region, city, lat, lon, weight in D.READER_CITIES
                  for _ in range(weight)]
        # Inside the retention window, which the nightly purge enforces.
        oldest = NOW - timedelta(days=traffic.RETENTION_DAYS - 2)
        db = self.db()
        opened = 0
        try:
            rows = db.execute(text(
                "SELECT id, published_at, helpful_votes FROM reviews "
                "WHERE published_at IS NOT NULL AND NOT is_removed ORDER BY review_id")).all()
            for review_id, published, helpful in rows:
                start = max(published, oldest)
                span = (NOW - start).total_seconds()
                total = (helpful or 0) * rng.randint(6, 14) + rng.randint(15, 45)
                moments = [start + timedelta(seconds=span * rng.random() ** 1.8)
                           for _ in range(rng.randint(8, 14))]
                moments.append(NOW - timedelta(hours=rng.randint(2, 140)))
                cuts = sorted(rng.sample(range(1, total), len(moments) - 1))
                sizes = [b - a for a, b in zip([0, *cuts], [*cuts, total], strict=True)]
                for when, size in zip(moments, sizes, strict=True):
                    traffic.record_view(db, review_id, now=when, count=size)
                    traffic.record(db, rng.choice(cities), now=when, count=size)
                    opened += size
            db.commit()
        finally:
            db.close()
        self.note(f"{opened} review opens across {len(D.READER_CITIES)} cities")

    # ------------------------------------------------------------ settle

    def _chronology(self) -> int:
        """Nothing answers what it replies to before that exists.

        Children are dated relative to their parent's day with a plausible
        hour, and `ago` sets the hour after subtracting days. Seeded just after
        midnight UTC, a vote meant for 0.2 days after its review landed on the
        review's own date at an earlier hour (the first TEST run's `verify`
        caught it). Whatever the hour the seed runs, move any child that
        precedes its parent to a deterministic moment shortly after it.
        """
        from sqlalchemy import text

        after = ("LEAST({parent} + make_interval(mins => 20 + abs(hashtext({child}.id::text)) "
                 "% 600), now() - interval '5 minutes')")
        repairs = (
            ("review_votes", "v", "reviews", "r", "r.id = v.review_id",
             "v.created_at < r.published_at", "r.published_at"),
            ("review_comments", "c", "reviews", "r", "r.id = c.review_id AND c.parent_id IS NULL",
             "c.created_at < r.published_at", "r.published_at"),
            ("review_comments", "c", "review_comments", "p", "p.id = c.parent_id",
             "c.created_at < p.created_at", "p.created_at"),
            ("answers", "a", "questions", "q", "q.id = a.question_id",
             "a.created_at < q.created_at", "q.created_at"),
        )
        moved = 0
        db = self.db()
        try:
            for table, c, parent_table, p, join, wrong, parent_at in repairs:
                at = after.format(parent=parent_at, child=c)
                moved += db.execute(text(f"""
                    WITH t(id, at) AS (
                        SELECT {c}.id, {at} FROM {table} {c} JOIN {parent_table} {p} ON {join}
                         WHERE {wrong})
                    UPDATE {table} x SET created_at = t.at, updated_at = t.at
                      FROM t WHERE t.id = x.id""")).rowcount or 0
            db.commit()
        finally:
            db.close()
        return moved

    def settle(self) -> None:
        """Recompute what the platform derives, after history has been back-dated."""
        from sqlalchemy import select, text

        from app.models.review import Review
        from app.services.review_service import recompute_product_aggregates
        from app.services.trust_service import recompute_user_trust
        from app.services.vote_service import recompute_review_vote_aggregates

        reordered = self._chronology()
        if reordered:
            self.note(f"{reordered} replies and votes re-dated after what they answer")
        db = self.db()
        try:
            for rid in self.review.values():
                review = db.get(Review, uuid.UUID(rid))
                if review is not None:
                    recompute_review_vote_aggregates(db, review)
            for pid in self.product.values():
                recompute_product_aggregates(db, uuid.UUID(pid))
            db.commit()
            # Two passes: a voter's stage feeds the evidence of the people they
            # voted for, so settle stages first, then evidence.
            for _ in range(2):
                for uid in self.uid.values():
                    recompute_user_trust(db, uuid.UUID(uid))
                db.commit()
            # Moderation-log and notification times follow the events they record.
            db.execute(text("""
                UPDATE notifications n SET created_at = sub.at
                  FROM (SELECT n2.id, coalesce(
                           (SELECT max(a.created_at) FROM answers a
                             WHERE n2.link = '/questions/' || a.question_id::text),
                           (SELECT max(c.created_at) FROM review_comments c
                             WHERE n2.link LIKE '/reviews/' || c.review_id::text || '%'),
                           (SELECT r.published_at FROM reviews r
                             WHERE n2.link LIKE '/reviews/' || r.id::text || '%'))
                           AS at FROM notifications n2) sub
                 WHERE sub.id = n.id AND sub.at IS NOT NULL AND sub.at < n.created_at
            """))
            # Anything older than two weeks has been seen.
            db.execute(text("UPDATE notifications SET read_at = created_at + interval '1 day' "
                            "WHERE read_at IS NULL AND created_at < now() - interval '14 days'"))
            db.commit()
            stages = dict(db.execute(select(text("username"), text("trust_stage"))
                                     .select_from(text("users"))
                                     .where(text("username = ANY(:u)")),
                                     {"u": [p.username for p in D.PERSONAS]}).all())
        finally:
            db.close()
        self.note("trust stages: " + ", ".join(f"{u} {s}" for u, s in sorted(stages.items())))

    def audit(self) -> None:
        """Date the moderators' audit trail from what each entry acted on.

        Every decision above was made through the API a moment ago, so the
        activity log and "Approved today" would otherwise say the whole history
        happened this morning. The entries themselves are untouched - only
        their time moves, to when that decision would have been made.
        """
        def settled(moment: str) -> str:
            return f"LEAST({moment}, now() - interval '3 hours')"

        h = "abs(hashtext(m.id::text))"
        on_review = "FROM moderation_logs m JOIN reviews r ON r.id = m.target_ref"
        rules = (
            # Earnings decisions: a day or two after the review went up.
            f"""SELECT m.id,
                       {settled(f"r.published_at + make_interval(hours => 12 + {h} % 36)")}
                  {on_review} WHERE m.action IN ('approve', 'reject')""",
            # The affiliate link: after the decision, before any order through it.
            f"""SELECT m.id, {settled(
                    "r.published_at + make_interval(hours => 50 + abs(hashtext(r.id::text)) % 10)")}
                  {on_review} WHERE m.action = 'affiliate_link_attach'""",
            # The gate's check runs as votes arrive, across the review's life.
            f"""SELECT m.id, r.published_at + (now() - r.published_at) * (({h} % 1000) / 1000.0)
                  {on_review} WHERE m.action = 'cold_start_substitution'""",
            f"""SELECT m.id, coalesce(r.removed_by_author_at, now() - interval '4 days')
                  {on_review} WHERE m.action = 'author_delete'""",
            """SELECT m.id, p.created_at + interval '25 minutes'
                  FROM moderation_logs m JOIN products p ON p.id = m.target_ref
                 WHERE m.action IN ('alias_add', 'listing_attach')""",
            """SELECT m.id, coalesce(q.best_answer_picked_at, a.created_at + interval '1 day')
                  FROM moderation_logs m JOIN answers a ON a.id = m.target_ref
                  JOIN questions q ON q.id = a.question_id
                 WHERE m.action = 'best_answer_pick'""",
            """SELECT m.id, mr.received_on + time '10:00' AT TIME ZONE 'Asia/Manila'
                  FROM moderation_logs m JOIN marketplace_remittances mr
                    ON mr.platform::text = m.context->>'platform'
                   AND mr.cycle_month::text = m.context->>'cycle_month'
                 WHERE m.action = 'remittance_record'""",
            # A cashout's entry names its member and amount, not the payout row.
            """SELECT m.id, p.created_at FROM moderation_logs m
                  JOIN payouts p ON p.user_id = m.target_ref
                   AND p.amount = (m.context->>'amount')::numeric
                 WHERE m.action = 'cashout_request'""",
            """SELECT m.id, (SELECT max(b.received_at) FROM affiliate_postbacks b
                   WHERE b.platform::text = split_part(m.context->>'format', '_', 1))
                  FROM moderation_logs m WHERE m.action = 'csv_import'""",
            """SELECT m.id, CASE m.action WHEN 'seller_appeal' THEN a.created_at
                                        ELSE a.substantiation_requested_at END
                  FROM moderation_logs m JOIN seller_review_appeals a
                    ON a.seller_review_id = m.target_ref
                 WHERE m.action IN ('seller_appeal', 'substantiation_request')""",
            # The system's concentration hold, then the moderator's investigation.
            """SELECT m.id, now() - interval '3 days 4 hours' FROM moderation_logs m
                 WHERE m.action = 'report' AND m.reporter_id IS NULL""",
            """SELECT m.id, now() - interval '2 days 1 hour' FROM moderation_logs m
                 WHERE m.action = 'investigation_set'""",
        )
        # Rows the API stamped "now" that the entries below are dated from.
        sources = (
            # The asker picks a Best Answer a day after it arrives.
            """UPDATE questions q SET best_answer_picked_at =
                      LEAST(a.created_at + interval '1 day', now() - interval '3 hours')
                 FROM answers a WHERE a.id = q.best_answer_id
                  AND q.best_answer_picked_at > now() - interval '1 hour'""",
            """UPDATE reviews SET removed_by_author_at = now() - interval '4 days'
                WHERE removed_by_author_at > now() - interval '1 hour'""",
            # The store appeals a review two days after it, and is asked to back
            # the appeal up the day after.
            """UPDATE seller_review_appeals a
                  SET created_at = sr.created_at + interval '2 days',
                      updated_at = sr.created_at + interval '3 days',
                      substantiation_requested_at = CASE WHEN a.substantiation_requested_at
                          IS NULL THEN NULL ELSE sr.created_at + interval '3 days' END
                 FROM seller_reviews sr
                WHERE sr.id = a.seller_review_id AND a.created_at > now() - interval '1 hour'""",
        )
        db = self.db()
        moved = 0
        try:
            for sql in sources:
                db.execute(text(sql))
            for sql in rules:
                moved += db.execute(text(f"""
                    WITH t(id, at) AS ({sql})
                    UPDATE moderation_logs m SET created_at = t.at, updated_at = t.at
                      FROM t WHERE t.id = m.id AND t.at IS NOT NULL""")).rowcount or 0
            # A link row dates from the moderator attaching it.
            db.execute(text("""
                UPDATE referral_links l SET created_at = m.created_at, updated_at = m.created_at
                  FROM moderation_logs m
                 WHERE m.action = 'affiliate_link_attach' AND m.target_ref = l.review_id"""))
            db.execute(text("""
                UPDATE marketplace_remittances SET created_at =
                       received_on + time '10:00' AT TIME ZONE 'Asia/Manila'"""))
            for spec in D.REPORTS:
                filed = NOW - timedelta(hours=spec.hours_ago)
                decided = filed + timedelta(hours=18) if spec.resolution else None
                moved += db.execute(text("""
                    UPDATE moderation_logs SET created_at = :f, updated_at = coalesce(:d, :f),
                           resolved_at = CASE WHEN resolved_at IS NULL THEN NULL ELSE :d END
                     WHERE action = 'report' AND reporter_id = :u AND target_ref = :r"""),
                    {"f": filed, "d": decided, "u": self.uid[spec.reporter],
                     "r": self.review[spec.review]}).rowcount or 0
            db.commit()
            left = db.scalar(text("SELECT count(*) FROM moderation_logs "
                                  "WHERE created_at > now() - interval '1 hour'"))
        finally:
            db.close()
        self.note(f"audit trail dated: {moved} entries moved, {left} left at seed time")

    # ------------------------------------------------------------ run

    def run(self) -> dict:
        steps = (self.people, self.products, self.stores, self.reviews, self.decisions,
                 self.updates_and_deletes, self.votes, self.gate_votes, self.comments,
                 self.questions,
                 self.store_reviews, self.prices, self.money, self.moderation,
                 self.integrity, self.requests, self.traffic, self.settle, self.audit)
        for step in steps:
            print(f"[defense] {step.__name__}", flush=True)
            step()
        return {
            "target": self.kind,
            "seeded_at": NOW.isoformat(),
            "personas": {p.key: {"username": p.username, "email": email_for(p, self.email_base),
                                 "id": self.uid[p.key]} for p in D.PERSONAS},
            "products": self.product, "stores": self.store, "reviews": self.review,
            "questions": self.question, "log": self.log,
        }


def already_seeded() -> bool:
    from sqlalchemy import text

    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        return bool(db.execute(text(
            "SELECT 1 FROM users WHERE email LIKE '%@demo.bluntly.ph' LIMIT 1")).first())
    finally:
        db.close()


#: Where the personas' "+" aliases route when DEFENSE_EMAIL_BASE is unset: the
#: brand's published contact inbox (the /contact page). A mailbox for one-time
#: codes, never an authorization identity — nothing grants a role by email.
TEAM_INBOX = "bluntly.ph@gmail.com"


def main(argv: list[str] | None = None) -> int:

    parser = argparse.ArgumentParser(description="Seed the capstone-defense dataset.")
    parser.add_argument("--reset", action="store_true",
                        help="clear the database first (scripts.defense.reset --apply)")
    parser.add_argument("--out", default=None, help="write ids and personas as JSON here")
    parser.add_argument("--email-base", default=None,
                        help="inbox the personas' '+' aliases route to "
                             "(default: DEFENSE_EMAIL_BASE, else the team inbox)")
    parser.add_argument("--image-cache", default=None,
                        help="directory to cache downloaded product images")
    args = parser.parse_args(argv)
    kind = require_defense_target("seed")
    import os
    base = args.email_base or os.environ.get("DEFENSE_EMAIL_BASE") or TEAM_INBOX
    if "@" not in (base or ""):
        print("[defense] no email base: set DEFENSE_EMAIL_BASE", file=sys.stderr)
        return 2
    if args.reset:
        from scripts.defense.reset import reset
        reset(True, kind=kind)
    elif already_seeded():
        print("[defense] the dataset is already present; run with --reset to rebuild it",
              file=sys.stderr)
        return 3
    seeder = Seeder(kind, base, Path(args.image_cache) if args.image_cache else None)
    result = seeder.run()
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"[defense] seeded ({kind}) in {len(result['log'])} steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
