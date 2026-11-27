"""A proposed product name from a pasted marketplace link (QA-072).

"Never display a raw Shopee/Lazada URL as the product name." The reviewer
pastes a listing; this reads the product name the marketplace already put in
the link's own path — `shopee.ph/Anker-Soundcore-Q20i-i.123.456`,
`lazada.com.ph/products/anker-soundcore-q20i-i123-s456.html` — and offers it
as an editable *proposal*. A moderator still names the canonical product.

It never fetches the page. The owner ruled scraping out permanently
(2026-07-15, MILESTONES.md) and both marketplaces' terms prohibit it, so the
only "metadata" this may read is the URL the reviewer handed us. A link with no
name in it (a short link, `/product/<shop>/<item>`, `pdp-i123`) proposes
nothing, and the form asks for the name — a name is never made up.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

#: `…/Some-Product-Name-i.<shop>.<item>` — Shopee's canonical product path.
_SHOPEE = re.compile(r"^/(?P<slug>.+?)-i\.\d+\.\d+/?$")
#: `…/products/<slug>-i<item>(-s<sku>).html` — Lazada's.
_LAZADA = re.compile(r"^/products/(?P<slug>.+?)-i\d+(?:-s\d+)?\.html?$", re.IGNORECASE)
#: A slug that is only an id ("pdp", "i123") is not a name.
_ID_ONLY = re.compile(r"^(?:pdp|i\d+|s\d+|\d+)$", re.IGNORECASE)
_SPACES = re.compile(r"\s+")
#: What a typed "name" that is really a link looks like.
_URLISH = re.compile(r"(?:^|\s)(?:https?://|www\.)|^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}/\S*$",
                     re.IGNORECASE)
MAX_NAME = 160


def looks_like_url(text: str | None) -> bool:
    """True for "https://…", "www.…" and a bare "shopee.ph/…"."""
    value = (text or "").strip()
    return bool(value) and bool(_URLISH.search(value))


def proposed_name(url: str | None) -> str | None:
    """The product name written into a Shopee or Lazada listing link, or None."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    path = parts.path or ""
    if "shopee" in host:
        match = _SHOPEE.match(path)
    elif "lazada" in host:
        match = _LAZADA.match(path)
    else:
        return None
    if match is None:
        return None
    slug = unquote(match.group("slug")).replace("-", " ").replace("_", " ")
    name = _SPACES.sub(" ", slug).strip(" .")
    if len(name) < 3 or _ID_ONLY.match(name.replace(" ", "")) or looks_like_url(name):
        return None
    return name[:MAX_NAME]
