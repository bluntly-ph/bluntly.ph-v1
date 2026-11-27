"""The platform-wide link ban (Business Rules §1 and §20).

    "No links of any kind, anywhere on the platform - reviews, comments, Q&A,
    seller replies, bios - except the one official affiliate link an admin
    attaches after approval."

One policy, used by every free-text field through `reject_links`, so a new
surface opts in by calling one function rather than by someone re-deriving a
regex. It works in two steps on purpose:

1. **Normalise** what a person can do to disguise a link: Unicode
   compatibility forms (full-width letters, ligatures), zero-width and bidi
   control characters, the common Cyrillic/Greek look-alikes of Latin
   letters, percent-encoding, `hxxp`, and spelled-out dots (`[dot]`, `(.)`,
   `shopee dot ph`).
2. **Detect** on the normalised text: a scheme (`http:`, `https:`, `ftp:`,
   `javascript:`, `data:`, `vbscript:`), `www.`, a markdown link, an HTML
   anchor, or a bare domain whose last label is a real top-level domain.

The bare-domain check is deliberately anchored on a curated TLD list instead of
"anything with a dot": reviews are full of `4.5`, `e.g.`, `v2.1`, `USB-C.` and
`10000mAh`, and a ban that fires on those would be a ban nobody can write a
review under. The list covers generic TLDs people actually paste, the
marketplace and short-link hosts this market uses, and the country codes of
the region.

Nothing here tries to be a URL parser. The only question is "would a reader
recognise this as a place to go?", and the answer is allowed to be
conservative: a false positive costs a rephrase, a false negative is the exact
thing the rule forbids.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote

#: Invisible characters people use to split a URL so a filter misses it.
_INVISIBLE = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0x2061, 0x2062, 0x2063,
     0x2064, 0xFEFF, 0x00AD, 0x034F, 0x061C, 0x180E, 0x202A, 0x202B, 0x202C,
     0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069],
    None,
)

#: Cyrillic and Greek letters that render like Latin ones. NFKC does not fold
#: these (they are different letters, not different forms), so a link spelled
#: with them survives normalisation unless it is mapped here.
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "ԁ": "d", "ԛ": "q", "ԝ": "w",
    "А": "a", "В": "b", "Е": "e", "К": "k", "М": "m", "Н": "h", "О": "o",
    "Р": "p", "С": "c", "Т": "t", "Х": "x", "Ү": "y",
    "α": "a", "ο": "o", "ρ": "p", "ν": "v", "τ": "t", "κ": "k", "ι": "i",
    "Α": "a", "Β": "b", "Ε": "e", "Ζ": "z", "Η": "h", "Ι": "i", "Κ": "k",
    "Μ": "m", "Ν": "n", "Ο": "o", "Ρ": "p", "Τ": "t", "Υ": "y", "Χ": "x",
    "。": ".", "．": ".", "｡": ".", "∙": ".", "·": ".", "․": ".",
    "⁄": "/", "∕": "/", "／": "/", "：": ":",
})

#: Top-level domains a reader would recognise as the end of an address. Curated,
#: not exhaustive: see the module docstring for why this is not "any dot".
_TLDS = frozenset("""
com net org info biz io co app dev ai gg tv me ly to fm cc ws link site online
shop store xyz top club live world today tech space website page blog news
ph sg my id th vn jp kr cn hk tw au nz uk us ca de fr it es nl ru in br
asia mobi pro name cloud host digital email click one fun buzz icu
""".split())

#: Marketplace short-link hosts that do not end in a listed TLD (`shope.ee`),
#: kept so the rule does not depend on the TLD list for the likeliest offenders.
_KNOWN_LINK_HOSTS = ("shope.ee", "shp.ee", "s.lazada", "c.lazada", "amzn.to",
                     "bit.ly", "tinyurl", "t.co", "goo.gl", "rb.gy", "cutt.ly")

_SPELLED_DOT = re.compile(r"\s*[\[\(\{<]\s*(?:dot|\.)\s*[\]\)\}>]\s*", re.I)
_WORD_DOT = re.compile(r"(?<=[a-z0-9])\s+dot\s+(?=(?:" + "|".join(sorted(_TLDS)) + r")\b)", re.I)
_SPACED_DOT = re.compile(r"(?<=[a-z0-9])\s+\.\s+(?=[a-z])", re.I)
_HXXP = re.compile(r"\bh[x*]{2}p(s?)\b", re.I)

_SCHEME = re.compile(
    r"\b(?:https?|ftp|javascript|vbscript|mailto)\s*:|\bdata\s*:\s*[a-z]+/[a-z0-9.+-]+", re.I
)
# A bare IPv4 host, optionally with a port: "10.0.0.1:8080". Octets are bounded
# to 0-255 so "1.5x", "4.5/5" and prices never match, and a letter or a dot just
# before it ("v1.0.0.12", "ver.1.2.3.4") marks a version string, not a host.
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
_IPV4 = re.compile(rf"(?<![\w.]){_OCTET}(?:\.{_OCTET}){{3}}(?::\d{{1,5}})?(?![\w.])")
_WWW = re.compile(r"\bwww\d?\s*\.\s*[a-z0-9]", re.I)
_MARKDOWN = re.compile(r"\[[^\]\n]{0,200}\]\(\s*[^)\s]+\s*\)")
_HTML_ANCHOR = re.compile(r"<\s*a\b[^>]*\bhref\b", re.I)
_BARE_DOMAIN = re.compile(
    r"(?<![a-z0-9@._-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+([a-z]{2,24}))(?![a-z0-9-])"
    r"(?:[/:?#][^\s]*)?",
    re.I,
)


#: TLDs that are also ordinary words. After a period with no space ("It's the
#: best.Today I…") a capitalised one is a new sentence, not an address, so for
#: these the original casing decides. Country codes and com/net/org are not in
#: here: nobody starts a sentence with "Ph" or "Com".
_WORDLIKE_TLDS = frozenset("""
in it to me my us co id io am be do go no so tv fm cc ws one fun top pro
link site online shop store club live world today tech space website page
blog news cloud host digital email click name buzz app dev info biz asia
""".split())


def normalise(text: str, *, lower: bool = True) -> str:
    """The text as a link filter should see it. Never shown to anyone."""
    value = unicodedata.normalize("NFKC", text or "")
    value = value.translate(_INVISIBLE).translate(_CONFUSABLES)
    # Percent-encoding hides the scheme separator and the dots (`https%3A%2F%2F`).
    # Decoding twice catches the double-encoded form; a third pass adds nothing.
    for _ in range(2):
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded
    if lower:
        value = value.lower()
    value = _HXXP.sub(lambda m: "http" + m.group(1), value)
    value = _SPELLED_DOT.sub(".", value)
    value = _WORD_DOT.sub(".", value)
    value = _SPACED_DOT.sub(".", value)
    return value


def find_link(text: str | None) -> str | None:
    """The first thing in `text` a reader would treat as a link, or None."""
    if not text:
        return None
    value = normalise(text)
    for pattern in (_SCHEME, _WWW, _MARKDOWN, _HTML_ANCHOR, _IPV4):
        match = pattern.search(value)
        if match:
            return match.group(0)
    for host in _KNOWN_LINK_HOSTS:
        for found in re.finditer(re.escape(host), value):
            start, end = found.start(), found.end()
            before_ok = start == 0 or not value[start - 1].isalnum()
            after_ok = end == len(value) or not value[end].isalnum()
            if before_ok and after_ok:
                return host
    for match in _BARE_DOMAIN.finditer(normalise(text, lower=False)):
        tld = match.group(2)
        folded = tld.lower()
        labels = match.group(1).lower().split(".")
        if folded not in _TLDS:
            continue
        if folded in _WORDLIKE_TLDS and tld[0].isupper():
            continue
        # A domain needs a label with a letter in it before the TLD: `4.5.ph`
        # is not an address anyone types, `jisulife.ph` is.
        if any(re.search(r"[a-z]", label) for label in labels[:-1]):
            return match.group(0).lower()
    return None


LINK_REJECTION = (
    "Links aren't allowed in {field}. Bluntly shows only the official buy link a "
    "administrator attaches to an approved review, so please describe the place in "
    "words instead."
)


def reject_links(value: str | None, *, field: str) -> str | None:
    """Pydantic-friendly: return `value` unchanged, or raise ValueError."""
    if value and find_link(value) is not None:
        raise ValueError(LINK_REJECTION.format(field=field))
    return value


def reject_links_in_list(values: list[str] | None, *, field: str) -> list[str] | None:
    for value in values or []:
        reject_links(value, field=field)
    return values
