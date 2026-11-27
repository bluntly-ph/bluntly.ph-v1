"""Round 3 pure rules — no database (QA-067, QA-072, QA-075).

* the DTI/SEC format rule, held to the case table the claim form's own test
  reads, so client and server cannot disagree;
* the product name proposed from a pasted listing link, which never fetches;
* @mention parsing over plain text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.registration_format import format_error
from app.schemas.product import ProductCreate
from app.schemas.seller import SellerClaimCreate
from app.services.comment_service import MAX_MENTIONS, mentioned_usernames
from app.services.listing_names import looks_like_url, proposed_name

CASES = json.loads((Path(__file__).resolve().parents[2] / "shared"
                    / "registration-numbers.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['kind']}:{c['value']!r}")
def test_registration_format_matches_the_shared_case_table(case):
    assert (format_error(case["kind"], case["value"]) is None) is case["ok"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['kind']}:{c['value']!r}")
def test_the_claim_schema_enforces_the_same_rule(case):
    body = {"registration_kind": case["kind"], "registration_number": case["value"],
            "registered_business_name": "Test Trading", "marketplace_shop_name": "Shop"}
    if case["ok"]:
        assert SellerClaimCreate(**body).registration_number == case["value"].strip()
    else:
        with pytest.raises(ValidationError):
            SellerClaimCreate(**body)


def test_a_format_error_explains_itself_and_never_claims_verification():
    for case in CASES:
        message = format_error(case["kind"], case["value"])
        if message is not None:
            assert message and "verif" not in message.lower()


# --- QA-072: a name from the link, never a fetch -----------------------------

@pytest.mark.parametrize(("url", "name"), [
    ("https://shopee.ph/Anker-Soundcore-Q20i-Wireless-i.123456.7890123?sp_atk=abc",
     "Anker Soundcore Q20i Wireless"),
    ("https://www.lazada.com.ph/products/anker-soundcore-q20i-i123456-s789.html?spm=x",
     "anker soundcore q20i"),
    ("https://shopee.ph/product/123456/7890123", None),       # ids only
    ("https://www.lazada.com.ph/products/pdp-i123-s456.html", None),
    ("https://shp.ee/abc123", None),                          # short link
    ("https://s.lazada.com.ph/s.abc", None),
    ("https://example.com/Some-Name-i.1.2", None),            # not a marketplace
    ("", None),
    (None, None),
])
def test_proposed_name_reads_only_the_link(url, name):
    assert proposed_name(url) == name


def test_the_listing_module_cannot_fetch_anything():
    source = (Path(__file__).resolve().parents[1] / "app" / "services"
              / "listing_names.py").read_text()
    for forbidden in ("httpx", "requests", "urllib.request", "urlopen", "socket"):
        assert f"import {forbidden}" not in source and f"from {forbidden}" not in source


@pytest.mark.parametrize(("text", "urlish"), [
    ("https://shopee.ph/x", True), ("shopee.ph/abc-i.1.2", True), ("www.lazada.com.ph", True),
    ("Anker Q20i", False), ("Model 2.0 fan", False), ("v1.2/3", False),
])
def test_what_counts_as_a_link_for_a_name(text, urlish):
    assert looks_like_url(text) is urlish


def test_a_product_cannot_be_named_with_a_link():
    with pytest.raises(ValidationError):
        ProductCreate(name="https://shopee.ph/Anker-Q20i-i.1.2")
    with pytest.raises(ValidationError):
        ProductCreate(name="   ")
    assert ProductCreate(name="  Anker Q20i ").name == "Anker Q20i"


# --- QA-067: mentions ----------------------------------------------------------

def test_mentions_are_plain_text_usernames():
    assert mentioned_usernames("thanks @Kristine_V and @paolo!") == ["kristine_v", "paolo"]
    assert mentioned_usernames("mail me@example.com") == []           # not a mention
    assert mentioned_usernames("@ab too short") == []
    assert mentioned_usernames("@same @SAME @same") == ["same"]
    assert mentioned_usernames("<b>@bold</b>") == ["bold"]            # text, never markup
    many = " ".join(f"@user{i:02d}" for i in range(12))
    assert len(mentioned_usernames(many)) == MAX_MENTIONS
