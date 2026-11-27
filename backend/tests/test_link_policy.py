"""The platform-wide link ban (Business Rules §1, §20) — no database needed."""

import pytest

from app.core.link_policy import find_link, reject_links

BLOCKED = [
    "buy it at https://shopee.ph/product/1/2",
    "HTTP://LAZADA.COM.PH/products/x-i1.html",
    "see www.example.org for more",
    "go to jisulife.ph now",
    "cheaper on lazada.com.ph",
    "[click here](https://evil.example)",
    "[click here](evil)",
    '<a href="https://x.io">x</a>',
    "javascript:alert(1)",
    "JaVaScRiPt :alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "hxxps://shopee.ph/abc",
    "shopee[dot]ph/abc",
    "shopee (dot) ph",
    "shopee dot ph",
    "shopee . ph",
    "https%3A%2F%2Fshopee.ph",
    "https%253A%252F%252Fshopee.ph",
    "ｈｔｔｐｓ://ｓｈｏｐｅｅ.ｐｈ",          # full-width
    "shop\u200bee.ph",                         # zero-width space inside
    "https\u200b://x.com",
    "\u0455hopee.ph",                          # Cyrillic dze for s
    "sh\u043epee.ph",                          # Cyrillic o
    "grab it on shope.ee/abc",
    "bit.ly/3abc",
    "my store: sulit-deals.store",
    "ends with a domain example.com",
]

ALLOWED = [
    "Rating 4.5/5 — e.g. the fan lasts 8 hrs, i.e. a full commute.",
    "10000mAh power bank, v2.1 firmware, USB-C.",
    "It's the best.Today I used it for 3 hours.",
    "Worth it.In the box you get a cable.",
    "Mr.Smith recommended it. Salamat.po",
    "My data: 20GB per month is enough.",
    "Bought it on Shopee for P899.",
    "The Life9 is louder than the Life7.",
    "Price went from 1.299 to 999.",
    "the fan's grill.It feels premium",
    "I rate this 3.5 stars.",
    "",
]


@pytest.mark.parametrize("text", BLOCKED)
def test_links_are_found(text):
    assert find_link(text) is not None, text


@pytest.mark.parametrize("text", ALLOWED)
def test_ordinary_review_text_passes(text):
    assert find_link(text) is None, (text, find_link(text))


def test_reject_links_raises_a_readable_error():
    with pytest.raises(ValueError, match="Links aren't allowed in comments"):
        reject_links("see shopee.ph", field="comments")
    assert reject_links("plain words", field="comments") == "plain words"
    assert reject_links(None, field="comments") is None


# --- Full-system QA corpus (2026-09-24) -------------------------------------------
# Every form a reader would act on as a link, and ordinary review prose that must
# never be refused. Before this corpus, "10.0.0.1:8080" and "mailto:" got through.
# Plain email addresses are deliberately NOT links (contact details are covered
# by the "personal information" report reason, not the link ban).

HOSTILE = [
    "see http://example.com", "HTTPS://EXAMPLE.COM/x", "www.shopee.ph/deal",
    "shopee.ph/product-i.1.2", "lazada.com.ph", "bit.ly/3xYz", "tinyurl.com/abc",
    "s.lazada.com.ph/s.abc", "shp.ee/abc123", "go to example . com",
    "example[.]com", "example(dot)com", "hxxps://evil.com", "example。com",
    "exa\u200bmple.com", "ｅｘａｍｐｌｅ.ｃｏｍ",
    "[click](http://x.io)", '<a href="https://x.io">x</a>', "javascript:alert(1)",
    "data:text/html;base64,PHN2Zz4=", "http://192.168.0.1/admin", "visit 10.0.0.1:8080",
    "https%3A%2F%2Fevil.com", "https:%2F%2Fevil.com", "evil.co", "my site: foo.xyz",
    "example.io/path?q=1", "wa.me/639171234567", "t.me/somechannel", "fb.com/page",
    "HTTP://x.y", "https:/ /x.com", "ftp://files.example.org", "mailto:me@example.com",
]

ORDINARY = [
    "e.g. it is quiet", "i.e. the fan", "Mr. Smith said", "3.5mm jack", "v2.0 firmware",
    "Wi-Fi 6 works", "₱1,299.00 on sale", "etc. and so on", "1.5x faster", "It's 4.5/5",
    "U.S. plug", "No. 1 seller", "Rated 4.8.", "The end.Then it broke", "Model: XR-500.",
    "Dec. 25 delivery", "a.m. delivery", "10.5 inches", "USB-C 3.1", "Jan.2026 batch",
    "Worked ok...honestly", "OK.", "Vol.2", "ver.3", "Ph.D. level quiet", "5.0",
    "Great value!!! 10/10", "Size: M. Color: Blue.", "It is the best.I love it",
    "#1 fan", "@seller please reply", "50% off", "C++ fans", "firmware v1.0.0.12",
]


@pytest.mark.parametrize("text", HOSTILE)
def test_every_link_form_is_found(text):
    assert find_link(text), f"missed: {text!r}"


@pytest.mark.parametrize("text", ORDINARY)
def test_ordinary_prose_is_never_mistaken_for_a_link(text):
    assert find_link(text) is None, f"false positive: {text!r} -> {find_link(text)!r}"
