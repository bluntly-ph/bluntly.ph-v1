"""Review-queue tier chips count per facet (dev/QA sync 2026-09-29, ENG-0929-F).

"When you click the filters here, the others become zero, and only come back
when you click again." The tier chips above the queue are both counts and the
tier filter's toggles. They were counted over what the current filter kept,
so choosing one tier read every other tier as 0. Each chip now counts what
choosing it would show: every other filter still applied, the tier left out.
"""

from __future__ import annotations

import uuid

from tests.conftest import register_and_token, requires_db, set_trust_stage
from tests.test_priority_triage_api import _auth, _mod, _review

pytestmark = requires_db


def _page(client, mh, **params) -> dict:
    query = "&".join(f"{k}={v}" for k, v in {"limit": 100, **params}.items())
    res = client.get(f"/api/v1/admin/review-queue?{query}", headers=mh)
    assert res.status_code == 200, res.text
    return res.json()


def _two_tiers(client) -> tuple[str, dict]:
    """One High review (a Stage 0 first submission) and one Low (a trusted
    author's), both findable by a unique token."""
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    new_id, new_tok, _ = register_and_token(client)
    _review(client, _auth(new_tok), token)
    set_trust_stage(new_id, 0)
    old_id, old_tok, _ = register_and_token(client)
    _review(client, _auth(old_tok), f"{token} earlier")
    _review(client, _auth(old_tok), token)
    set_trust_stage(old_id, 3)
    return token, mh


def test_choosing_a_tier_keeps_the_other_tier_chips_counted(client):
    token, mh = _two_tiers(client)
    everything = _page(client, mh, q=token)["counts"]["by_tier"]
    assert everything["high"] >= 1 and everything["low"] >= 1

    low_only = _page(client, mh, q=token, tier="low")
    # The list is filtered...
    assert all(i["triage"]["tier"] == "low" for i in low_only["items"])
    assert low_only["total"] == everything["low"]
    # ...but the chips still say what each tier holds, so "High" does not read 0.
    assert low_only["counts"]["by_tier"] == everything


def test_the_tier_chips_still_honour_every_other_filter(client):
    token, mh = _two_tiers(client)
    other = uuid.uuid4().hex[:10]  # matches nothing
    none = _page(client, mh, q=other, tier="high")["counts"]["by_tier"]
    assert all(n == 0 for n in none.values())
    # Band and SLA chips are not toggles: they describe the current filter.
    low_only = _page(client, mh, q=token, tier="low")["counts"]
    assert sum(low_only["by_band"].values()) == low_only["total"]
