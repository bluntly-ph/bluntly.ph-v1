"""Suspicious duplicate text: pure comparison (QA, 2026-09-29).

Moderation evidence only. A match is never proof of plagiarism, never shown to
the public, and never blocks, removes or penalises anything: it files a
SYSTEM_DETECTED report for an Administrator (Business Rules §12).

Separate from product search on purpose (Business Rules §6, owner decision):
search forgives typos to FIND a product; this measures how much of one text
another reproduces. They share no code.

How two texts compare:

1. **Normalise** both: Unicode NFKC (full-width letters, ligatures), drop
   invisible format characters (zero-width spaces), strip accents, casefold,
   turn punctuation and symbols into spaces, collapse whitespace. Case, curly
   quotes, accents and padding cannot hide a copy.
2. **Only meaningful text is compared.** Below `MIN_TOKENS` words or
   `MIN_CHARS` characters, a text is never flagged: "Good product." written by
   two people is a coincidence, not plagiarism.
3. **Two measures**, the higher counts:
   - *near-identical*: Jaccard similarity of the character trigrams (the same
     measure `pg_trgm` uses to find candidates, on normalised text);
   - *copied passage*: the share of the shorter text's three-word phrases that
     appear in the other. This catches a copy with a sentence added or a few
     words swapped, which moves the first measure more.
4. **Flag** when near-identical ≥ `near_identical_threshold()` (0.85 by
   default: `settings.duplicate_similarity_threshold`, the threshold the check
   has always used), or when a copied passage covers ≥ `PASSAGE_SHARE`
   (0.70) of the shorter text AND spans at least `MIN_SHARED_PHRASES` (8)
   three-word phrases, so a common idiom is not a "passage".

Every number is a module constant, reported with each finding
(`ALGORITHM_VERSION`) and documented in docs/ANTI_FARMING_AND_PLAGIARISM.md.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.core.config import settings

ALGORITHM_VERSION = "text-dup-v1"
MIN_TOKENS = 12
MIN_CHARS = 60
PASSAGE_SHARE = 0.70
MIN_SHARED_PHRASES = 8
PHRASE_WORDS = 3

_SPACE = re.compile(r"\s+")


def near_identical_threshold() -> float:
    """`DUPLICATE_SIMILARITY_THRESHOLD`, 0.85 unless configured."""
    return float(settings.duplicate_similarity_threshold)


def normalize(text: str | None) -> str:
    """Text reduced to what a copy cannot change without rewriting it."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text))
    kept = []
    for ch in decomposed:
        cat = unicodedata.category(ch)
        if cat == "Mn" or cat == "Cf":      # accents; zero-width and other format chars
            continue
        if cat[0] in ("P", "S", "Z", "C"):   # punctuation, symbols, separators, controls
            kept.append(" ")
            continue
        kept.append(ch)
    return _SPACE.sub(" ", "".join(kept).casefold()).strip()


def tokens(normalized: str) -> list[str]:
    return normalized.split() if normalized else []


def is_meaningful(normalized: str) -> bool:
    """Long enough that a match means something."""
    return len(normalized) >= MIN_CHARS and len(tokens(normalized)) >= MIN_TOKENS


def _trigrams(normalized: str) -> set[str]:
    padded = f"  {normalized} "
    return {padded[i:i + 3] for i in range(len(padded) - 2)}


def _phrases(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + PHRASE_WORDS]) for i in range(len(words) - PHRASE_WORDS + 1)}


@dataclass(frozen=True)
class TextComparison:
    near_identical: float     # character-trigram Jaccard, 0..1
    passage_share: float      # shorter text's 3-word phrases found in the other, 0..1
    shared_phrases: int
    both_meaningful: bool

    @property
    def score(self) -> float:
        return max(self.near_identical, self.passage_share)

    @property
    def flagged(self) -> bool:
        if not self.both_meaningful:
            return False
        if self.near_identical >= near_identical_threshold():
            return True
        return self.passage_share >= PASSAGE_SHARE and self.shared_phrases >= MIN_SHARED_PHRASES

    @property
    def reason(self) -> str:
        """One plain sentence for the evidence panel. States what was measured."""
        if self.near_identical >= near_identical_threshold():
            return (f"Near-identical text: {round(self.near_identical * 100)}% of its "
                    "character sequences match.")
        return (f"Copied passage: {round(self.passage_share * 100)}% of the shorter text's "
                f"three-word phrases ({self.shared_phrases}) appear in the other.")


def compare(a: str | None, b: str | None) -> TextComparison:
    """Compare two raw texts. Symmetric."""
    na, nb = normalize(a), normalize(b)
    meaningful = is_meaningful(na) and is_meaningful(nb)
    if not na or not nb:
        return TextComparison(0.0, 0.0, 0, meaningful)
    ta, tb = _trigrams(na), _trigrams(nb)
    jaccard = len(ta & tb) / len(ta | tb)
    pa, pb = _phrases(tokens(na)), _phrases(tokens(nb))
    shared = len(pa & pb)
    shorter = min(len(pa), len(pb))
    share = shared / shorter if shorter else 0.0
    return TextComparison(round(jaccard, 4), round(share, 4), shared, meaningful)
