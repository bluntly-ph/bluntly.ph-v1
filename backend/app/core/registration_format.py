"""DTI / SEC registration number *format* (QA-075).

A sanity check on shape, the same one the claim form runs before Submit
enables (`lib/registration-format.ts`). Both are held to one case table,
`shared/registration-numbers.json`, by a test on each side.

It is not verification. Bluntly has no authoritative integration with the DTI
Business Name Registration System or the SEC, so passing this proves nothing
about whether a registration exists or whom it belongs to. Ownership is still
decided the way Business Rules §9 says: a moderator checks the registration
against the shop name on the marketplace. Nothing may call a claim "verified"
because its number is well-formed.

* **DTI** — a Business Name registration number: 6 to 10 digits, optionally
  written after "DTI" ("DTI-3318207"). Spaces and hyphens as separators are
  ignored.
* **SEC** — the company registration number: up to three letters (CS, CN, PG,
  A…) then 5 to 15 digits, with one optional two-to-four digit branch suffix
  after a hyphen ("2021030012345-01"). Spaces are ignored; case is not.
* **Placeholders** are refused on both: one digit repeated ("0000000"), or an
  ascending run from 0 or 1 ("1234567").
"""

from __future__ import annotations

import re

_DTI = re.compile(r"^[0-9]{6,10}$")
_SEC = re.compile(r"^[A-Z]{0,3}[0-9]{5,15}(?:-[0-9]{2,4})?$")
_ASCENDING = "01234567890123456789"


def normalize(kind: str, value: str | None) -> str:
    """The form the rule is checked on (not what is stored)."""
    raw = re.sub(r"\s+", "", (value or "").strip().upper())
    if kind == "dti":
        raw = raw.replace("-", "")
        return raw[3:] if raw.startswith("DTI") else raw
    return raw


def _placeholder(digits: str) -> bool:
    return bool(digits) and (len(set(digits)) == 1 or digits in _ASCENDING)


def format_error(kind: str, value: str | None) -> str | None:
    """Why `value` is not a well-formed number of this kind, or None if it is."""
    number = normalize(kind, value)
    if not number:
        return "Enter the registration number."
    if kind == "dti":
        if not _DTI.match(number):
            return "A DTI business name number is 6 to 10 digits."
        digits = number
    elif kind == "sec":
        if not _SEC.match(number):
            return ("An SEC registration number is up to three letters, then 5 to 15 "
                    "digits (for example CS201012345).")
        digits = re.sub(r"[^0-9]", "", number.split("-", 1)[0])
    else:
        return "Choose DTI or SEC."
    if _placeholder(digits):
        return "That looks like a placeholder, not a registration number."
    return None
