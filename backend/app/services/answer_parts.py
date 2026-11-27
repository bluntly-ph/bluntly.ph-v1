"""The structured answer (meeting 2026-10-02, 1:04-2:20): "very similar to the
review flow" — what the asker asked for (experience, pros & cons, would you
recommend it, is it right for me, a rating) plus the good, the bad and photos.

No migration. The question already carries its requested specifics as its last
line ("Looking for: Experience, Rating", components/qa/ask-question-model.ts);
an answer carries its parts the same way, as labelled lines after its own
words, so every surface that shows `body` (notifications, search, the admin
queue, older pages) still reads naturally, and this module reads them back:

    I bought it for my commute and it still holds up.

    Experience: Three months of daily use.
    Good: Battery lasts all day.
    Bad: The clip is flimsy.
    Recommends it: Yes
    Right for you: Yes, if you walk a lot.
    Rating: 4.5/5
    Photos: https://.../review-photos/<user>/<id>.jpg

Only an exact trailing block of known labels is parsed back out; anything else
stays the answer's own text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

#: The question's specifics, as the ask flow writes them.
REQUIREMENTS = ("Experience", "Pros & Cons", "Do you recommend this?",
                "Is this right for me?", "Rating")
_LOOKING_FOR = "Looking for: "

#: Labels in the order they are written.
LABELS = {
    "experience": "Experience",
    "good": "Good",
    "bad": "Bad",
    "recommend": "Recommends it",
    #: The verdict's optional "Why?" (Answer Step 4.1), on its own line.
    "verdict_reason": "Verdict reason",
    "right_for_you": "Right for you",
    "rating": "Rating",
    "photos": "Photos",
}
_BY_LABEL = {v: k for k, v in LABELS.items()}
MAX_PHOTOS = 4

#: The answer flow's "Your verdict" (Figma Answer Page - Step 4, 7573:8635),
#: written on the "Recommends it" line. Yes / No are the older two values.
VERDICTS = {
    "yes": "Yes",
    "on_sale": "Only on sale",
    "other_variant": "A different variant",
    "no": "No",
}
_VERDICT_BY_TEXT = {v: k for k, v in VERDICTS.items()}


@dataclass
class AnswerParts:
    text: str = ""
    experience: str | None = None
    good: str | None = None
    bad: str | None = None
    recommend: bool | None = None
    right_for_you: str | None = None
    rating: Decimal | None = None
    photo_urls: list[str] = field(default_factory=list)
    #: yes / on_sale / other_variant / no; `recommend` is True only for yes and
    #: False only for no (a qualified verdict is neither).
    verdict: str | None = None
    #: "Why? (optional)" under the verdict (Answer Step 4.1). Always optional.
    verdict_reason: str | None = None

    def __post_init__(self) -> None:
        if self.verdict is None and self.recommend is not None:
            self.verdict = "yes" if self.recommend else "no"
        elif self.verdict is not None:
            self.recommend = {"yes": True, "no": False}.get(self.verdict)

    @property
    def structured(self) -> bool:
        return any((self.experience, self.good, self.bad, self.right_for_you,
                    self.verdict_reason, self.verdict is not None, self.rating is not None,
                    self.photo_urls))


def requirements_of(question_body: str) -> list[str]:
    """The specifics a question asks for, from its "Looking for:" last line."""
    last = question_body.rsplit("\n", 1)[-1] if "\n" in question_body else ""
    if not last.startswith(_LOOKING_FOR):
        return []
    items = last[len(_LOOKING_FOR):].split(", ")
    return items if items and all(i in REQUIREMENTS for i in items) else []


#: Structured Q&A (owner 2026-10-05; docs/STRUCTURED_QUESTIONS_FIGMA_SPEC.md):
#: the answer part each requested specific makes REQUIRED, in the answer flow's
#: step order. "Rating" may sit on an older question's line; a rating is
#: required on every answer anyway, so it adds nothing here.
PART_FOR_REQUIREMENT = {
    "Experience": "experience",
    "Pros & Cons": "pros_cons",
    "Do you recommend this?": "verdict",
    "Is this right for me?": "fit",
}
PART_ORDER = ("experience", "pros_cons", "verdict", "fit")


def requested_parts(question_body: str) -> list[str]:
    """The answer parts a question's "Looking for:" line requires, each once,
    in step order. A legacy or free-form question requires none."""
    wanted = {PART_FOR_REQUIREMENT[r] for r in requirements_of(question_body)
              if r in PART_FOR_REQUIREMENT}
    return [p for p in PART_ORDER if p in wanted]


def _filled(value: str | None) -> bool:
    return bool(value and value.strip())


def missing_parts(parts: AnswerParts, required: list[str]) -> list[str]:
    """Which of the `required` parts this answer leaves empty, in step order."""
    present = {
        "experience": _filled(parts.experience),
        "pros_cons": _filled(parts.good) and _filled(parts.bad),
        "verdict": parts.verdict is not None,
        "fit": _filled(parts.right_for_you),
    }
    return [p for p in required if not present[p]]


def _one_line(value: str) -> str:
    return " ".join(value.split())


def compose(parts: AnswerParts) -> str:
    """The body to store: the answer's words, then its labelled parts."""
    lines = []
    for key in ("experience", "good", "bad"):
        value = getattr(parts, key)
        if value and value.strip():
            lines.append(f"{LABELS[key]}: {_one_line(value)}")
    if parts.verdict is not None:
        lines.append(f"{LABELS['recommend']}: {VERDICTS[parts.verdict]}")
    if parts.verdict_reason and parts.verdict_reason.strip():
        lines.append(f"{LABELS['verdict_reason']}: {_one_line(parts.verdict_reason)}")
    if parts.right_for_you and parts.right_for_you.strip():
        lines.append(f"{LABELS['right_for_you']}: {_one_line(parts.right_for_you)}")
    if parts.rating is not None:
        lines.append(f"{LABELS['rating']}: {parts.rating.normalize():f}/5")
    if parts.photo_urls:
        lines.append(f"{LABELS['photos']}: {' '.join(parts.photo_urls)}")
    text = parts.text.strip()
    if not lines:
        return text
    return f"{text}\n\n" + "\n".join(lines) if text else "\n".join(lines)


def parse(body: str) -> AnswerParts:
    """Read the labelled block back out; a body without one is all text."""
    lines = body.split("\n")
    start = len(lines)
    while start > 0:
        label, sep, _ = lines[start - 1].partition(": ")
        if not sep or label not in _BY_LABEL:
            break
        start -= 1
    block = lines[start:]
    if not block:
        return AnswerParts(text=body)
    out = AnswerParts(text="\n".join(lines[:start]).rstrip())
    for line in block:
        label, _, value = line.partition(": ")
        key = _BY_LABEL[label]
        value = value.strip()
        if key == "recommend":
            out.verdict = _VERDICT_BY_TEXT.get(value)
            out.recommend = {"yes": True, "no": False}.get(out.verdict or "")
        elif key == "rating":
            try:
                out.rating = Decimal(value.removesuffix("/5"))
            except ArithmeticError:
                out.rating = None
        elif key == "photos":
            out.photo_urls = [u for u in value.split(" ") if u][:MAX_PHOTOS]
        else:
            setattr(out, key, value)
    return out
