"""Why was this reported? (dev/QA sync 2026-09-29, ENG-0929-B.)

"Open the reported item" took an administrator to the review and left them to
work out on their own why anyone had flagged it. This module writes the
answer from what is stored, and nothing else:

* a member's report: its category, the reporter's own note, how many reports
  the item has, and why it escalated (an urgent reason, the weighted
  threshold, or a burst);
* a system report: the signal that fired and the evidence the integrity sweep
  stored with it (the matched review and its similarity, the reciprocal
  up-voters, the burst size, the cohort behind a held promotion).

Deterministic by construction: plain templates over stored fields. No
generative text, no confidence the checks did not compute. A signal filed
before its evidence was stored says so, rather than reconstructing a match
it never recorded. Reverse-image search is not claimed anywhere: no provider
is configured in this build (ADR-007).
"""

from __future__ import annotations

from dataclasses import dataclass, field

REASON_LABELS = {
    "safety_threat": "Threat or safety risk",
    "personal_information": "Personal information",
    "fake_proof": "Fake photo or receipt",
    "plagiarized": "Copied from elsewhere",
    "spam": "Spam",
    "harassment": "Harassment or abuse",
    "conflict_of_interest": "Undisclosed conflict of interest",
    "seller_posing_as_buyer": "Seller posing as a buyer",
    "counterfeit": "Counterfeit product",
    "other": "Something else",
}

SIGNAL_LABELS = {
    "duplicate_content": "Copied text",
    "duplicate_image": "Reused photo",
    "shared_network_votes": "Accounts sharing a network",
    "collusion": "Vote collusion",
    "vote_velocity": "Voting speed",
    "verdict_star_mismatch": "Verdict and stars disagree",
    "vote_concentration": "Vote concentration",
}

VERDICT_LABELS = {
    "yes_absolutely": "Yes, absolutely",
    "it_depends": "It depends",
    "hard_pass": "Hard pass",
}

KIND_NOUNS = {
    "review": "review",
    "comment": "comment",
    "seller_review": "store review",
    "user": "member",
    "answer": "answer",
    "question": "question",
    "seller": "store",
}


@dataclass(frozen=True)
class EvidenceLine:
    label: str
    value: str
    #: A same-site path when the fact is another item (the matched review).
    link: str | None = None


@dataclass(frozen=True)
class Explanation:
    summary: str
    #: The system signal that filed it; None for a member's report.
    signal: str | None = None
    signal_label: str | None = None
    evidence: list[EvidenceLine] = field(default_factory=list)
    #: False for a system report filed before its evidence was stored.
    evidence_stored: bool = True


def _pct(share: float) -> str:
    return f"{round(100 * share)}%"


def explain(*, origin: str, reason: str | None, notes: str | None,
            target_type: str | None, context: dict | None,
            report_count: int = 1, weighted: float = 0.0, escalated: bool = False,
            urgent: bool = False, surge: bool = False,
            matched: dict[str, tuple[str | None, str]] | None = None) -> Explanation:
    """The deterministic explanation of one report. `matched` maps a review id
    the evidence names to its (title, link), looked up by the caller."""
    kind = KIND_NOUNS.get(target_type or "", "item")
    context = context or {}
    if origin == "system_detected":
        return _system(kind, context, matched or {})
    return _member(kind, reason, notes, report_count, weighted, escalated, urgent, surge)


def _member(kind: str, reason: str | None, notes: str | None, report_count: int,
            weighted: float, escalated: bool, urgent: bool, surge: bool) -> Explanation:
    label = REASON_LABELS.get(reason or "", "Something else")
    parts = [f"A member reported this {kind} as “{label}”."]
    evidence = [EvidenceLine("Category", label)]
    if notes and notes.strip():
        parts.append(f"Their note: “{notes.strip()}”.")
        evidence.append(EvidenceLine("Reporter’s note", notes.strip()))
    if report_count > 1:
        parts.append(f"This {kind} has {report_count} reports in all.")
    evidence.append(EvidenceLine("Reports on this item", str(report_count)))
    evidence.append(EvidenceLine("Weighted open reports", f"{weighted:.2f} (escalates at 1.00)"))
    if escalated:
        if urgent:
            parts.append(f"It escalated at once: “{label}” is an urgent reason.")
        elif surge:
            parts.append("It escalated on a burst of reports against its usual rate.")
        else:
            parts.append("Reports from trusted members add up past the escalation "
                         "threshold.")
    return Explanation(summary=" ".join(parts), evidence=evidence)


def _system(kind: str, context: dict, matched: dict[str, tuple[str | None, str]]
            ) -> Explanation:
    signal = context.get("signal")
    stored = context.get("evidence")
    label = SIGNAL_LABELS.get(signal or "", "Automated check")
    tail = " Automated checks are advisory: nothing was changed automatically."

    if signal == "vote_concentration":
        # The trust hold writes its facts straight into the context.
        share = context.get("cohort_share")
        if share is None:
            return _unstored(signal, label, "A member’s votes came mostly from a small "
                             "repeated group.", tail)
        summary = (f"Vote concentration: {_pct(float(share))} of this member’s counted "
                   f"votes come from a repeated group of {context.get('cohort_size', 0)} "
                   f"voters. Their promotion to Stage {context.get('candidate_stage')} is "
                   f"held at Stage {context.get('held_at_stage')} until an administrator "
                   "decides.")
        held = (f"Stage {context.get('candidate_stage')} \u2192 held at Stage "
                f"{context.get('held_at_stage')}")
        evidence = [
            EvidenceLine("Distinct voters", str(context.get("distinct_voters", 0))),
            EvidenceLine("Eligible voters", str(context.get("eligible_voters", 0))),
            EvidenceLine("Repeated group", str(context.get("cohort_size", 0))),
            EvidenceLine("Share of counted votes", _pct(float(share))),
            EvidenceLine("Promotion held", held),
        ]
        return Explanation(summary=summary + tail, signal=signal, signal_label=label,
                           evidence=evidence)

    if not isinstance(stored, dict):
        generic = {
            "duplicate_content": "Possible copied review: the duplicate-text check matched "
                                 "this review against another one in the database.",
            "collusion": "Possible vote collusion: most of this review’s up-voters are "
                         "members its author up-votes back.",
            "vote_velocity": "Unusual voting speed: up-votes arrived faster than the "
                             "velocity check allows.",
            "verdict_star_mismatch": "The verdict and the star rating disagree.",
            "duplicate_image": "Possible reused photo: the photo matches another review's.",
            "shared_network_votes": "Possible vote farming: several accounts on one network "
                                    "up-voted this member.",
        }.get(signal or "", f"An automated integrity check flagged this {kind}.")
        return _unstored(signal, label, generic, tail)

    if signal == "duplicate_content":
        match_id = stored.get("duplicate_of")
        similarity = stored.get("similarity")
        # Evidence stored before 2026-09-29 names no kind: it was always a review.
        matched_kind = str(stored.get("matched_kind") or "review")
        fallback = f"/reviews/{match_id}" if matched_kind == "review" else None
        title, link = matched.get(str(match_id), (None, fallback)) \
            if match_id else (None, None)
        sim = f" ({round(100 * float(similarity))}% similar)" if similarity is not None else ""
        summary = (f"Possible copied {kind}: its text closely matches another {matched_kind} "
                   f"already in the database{sim}.")
        evidence = [EvidenceLine(f"Matching {matched_kind}",
                                 title or f"Untitled {matched_kind}", link)]
        if similarity is not None:
            evidence.append(EvidenceLine("Text similarity", f"{float(similarity):.2f}"))
        if stored.get("reason"):
            evidence.append(EvidenceLine("How it matched", str(stored["reason"])))
        if stored.get("algorithm"):
            evidence.append(EvidenceLine("Check", str(stored["algorithm"])))
        return Explanation(summary=summary + tail, signal=signal, signal_label=label,
                           evidence=evidence)

    if signal == "shared_network_votes":
        n = int(stored.get("accounts", 0))
        new = int(stored.get("new_accounts", 0))
        ups = int(stored.get("upvotes", 0))
        hours = int(stored.get("window_hours", 72))
        summary = (f"Possible vote farming: {n} accounts on one network up-voted this "
                   f"{kind}’s reviews {ups} times within {hours} hours ({new} of them under "
                   "30 days old). A household, office, school or mobile carrier can put "
                   "honest people on one network, so this is a signal to check against "
                   "the reviews’ voting, not proof. No IP address is stored or shown.")
        return Explanation(summary=summary + tail, signal=signal, signal_label=label,
                           evidence=[
                               EvidenceLine("Accounts on one network", str(n)),
                               EvidenceLine("Of them, under 30 days old", str(new)),
                               EvidenceLine("Up-votes on this member", str(ups)),
                               EvidenceLine("Reviews involved",
                                            str(len(stored.get("reviews") or []))),
                               EvidenceLine("Check", str(stored.get("algorithm", ""))),
                           ])

    if signal == "duplicate_image":
        match_id = stored.get("matched_review")
        title, link = matched.get(str(match_id), (None, f"/reviews/{match_id}")) \
            if match_id else (None, None)
        d = int(stored.get("distance", 0))
        bits = int(stored.get("hash_bits", 64))
        how = ("the identical file" if stored.get("identical_file")
               else f"{d} of {bits} bits apart in its image fingerprint")
        summary = (f"Possible reused photo: this {kind}’s photo matches the photo of an earlier "
                   f"review ({how}). A resized or re-saved copy still matches; two people "
                   "photographing the same item can too.")
        return Explanation(summary=summary + tail, signal=signal, signal_label=label,
                           evidence=[
                               EvidenceLine("Matching review", title or "Untitled review", link),
                               EvidenceLine("Fingerprint distance",
                                            f"{d} of {bits} bits (flagged at ≤ "
                                            f"{stored.get('threshold', 12)})"),
                               EvidenceLine("Check", str(stored.get("algorithm", ""))),
                           ])

    if signal == "collusion":
        n = int(stored.get("upvoters", 0))
        k = int(stored.get("reciprocal_upvoters", 0))
        threshold = float(stored.get("threshold", 0.6))
        minimum = int(stored.get("min_upvoters", 5))
        summary = (f"Possible vote collusion: {k} of this review’s {n} up-voters are "
                   "members whose own reviews its author up-votes. The check fires at "
                   f"{minimum} or more up-voters when more than {_pct(threshold)} of them "
                   "are reciprocal. It uses voting relationships only; no IP address or "
                   "location is collected for votes.")
        return Explanation(summary=summary + tail, signal=signal, signal_label=label,
                           evidence=[
                               EvidenceLine("Up-voters", str(n)),
                               EvidenceLine("Up-voted back by the author",
                                            f"{k} ({_pct(k / n) if n else '0%'})"),
                               EvidenceLine("Rule", f"≥ {minimum} up-voters and more "
                                            f"than {_pct(threshold)} reciprocal"),
                           ])

    if signal == "vote_velocity":
        m = int(stored.get("max_upvotes_in_window", 0))
        threshold = int(stored.get("threshold", 10))
        hours = int(stored.get("window_seconds", 3600)) // 3600 or 1
        window = "one hour" if hours == 1 else f"{hours} hours"
        summary = (f"Unusual voting speed: {m} up-votes arrived within {window}; the check "
                   f"fires above {threshold}.")
        return Explanation(summary=summary + tail, signal=signal, signal_label=label,
                           evidence=[EvidenceLine("Most up-votes in " + window, str(m)),
                                     EvidenceLine("Rule", f"more than {threshold}")])

    if signal == "verdict_star_mismatch":
        verdict = VERDICT_LABELS.get(stored.get("verdict") or "", "a verdict")
        stars = stored.get("star_rating")
        star_text = f"{float(stars):g}★" if stars is not None else "its stars"
        summary = (f"The verdict and the star rating disagree: “{verdict}” with "
                   f"{star_text}.")
        return Explanation(summary=summary + tail, signal=signal, signal_label=label,
                           evidence=[EvidenceLine("Verdict", verdict),
                                     EvidenceLine("Stars", star_text)])

    return _unstored(signal, label, f"An automated integrity check flagged this {kind}.", tail)


def _unstored(signal: str | None, label: str, sentence: str, tail: str) -> Explanation:
    return Explanation(
        summary=(sentence + " This report was filed before its evidence was stored; the "
                 "review’s Signals panel shows the current check." + tail),
        signal=signal, signal_label=label, evidence=[], evidence_stored=False)
