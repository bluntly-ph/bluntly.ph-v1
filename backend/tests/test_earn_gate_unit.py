"""The earn_eligible gate's queueing rule, without a database.

`maybe_queue` may only lift a public, undecided (`none`) review to `pending`,
only in the Post-Seeding Phase, and only when the gate passes. Anything a
moderator has decided stays decided.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models.enums import EarnEligibleStatus
from app.services import earn_gate


class _DB:
    """Just enough session for maybe_queue: it flushes before reading the gate,
    and records the queue entry for the admin priority tiers' aging clock."""

    def __init__(self):
        self.added = []

    def flush(self):
        pass

    def scalar(self, *_args, **_kwargs):
        return None  # no triage row yet

    def add(self, row):
        self.added.append(row)


def _review(status=EarnEligibleStatus.none, published=True, removed=False):
    return SimpleNamespace(id="r", earn_eligible_status=status, is_removed=removed,
                           published_at=datetime.now(UTC) if published else None,
                           # Only a thread's original review is queued (§4).
                           is_thread_root=True)


def _gate(passes: bool):
    return earn_gate.GateState(effective_positive=3, effective_total=3, wilson_lower_bound=0.9,
                               stage2_plus_voters=3, voters=3, passes=passes)


@pytest.fixture
def post_seeding(monkeypatch):
    monkeypatch.setattr(settings, "earn_gate_phase", "post_seeding")


def test_a_passing_gate_queues_an_undecided_public_review(post_seeding, monkeypatch):
    monkeypatch.setattr(earn_gate, "gate_state", lambda db, rid: _gate(True))
    review = _review()
    db = _DB()
    assert earn_gate.maybe_queue(db, review) is True
    assert review.earn_eligible_status == EarnEligibleStatus.pending
    # The moment it entered is recorded for triage aging — and nothing else.
    (entry,) = db.added
    assert (entry.queue, entry.target_type, entry.target_ref) == ("earnings", "review", "r")


def test_a_failing_gate_leaves_it_alone(post_seeding, monkeypatch):
    monkeypatch.setattr(earn_gate, "gate_state", lambda db, rid: _gate(False))
    review = _review()
    assert earn_gate.maybe_queue(_DB(), review) is False
    assert review.earn_eligible_status == EarnEligibleStatus.none


@pytest.mark.parametrize("status", [EarnEligibleStatus.pending, EarnEligibleStatus.approved,
                                    EarnEligibleStatus.rejected, EarnEligibleStatus.monetized,
                                    EarnEligibleStatus.honesty_fund])
def test_votes_never_reopen_or_override_a_decision(post_seeding, monkeypatch, status):
    monkeypatch.setattr(earn_gate, "gate_state", lambda db, rid: _gate(True))
    review = _review(status=status)
    assert earn_gate.maybe_queue(_DB(), review) is False
    assert review.earn_eligible_status == status


def test_taken_down_or_removed_reviews_are_never_queued(post_seeding, monkeypatch):
    monkeypatch.setattr(earn_gate, "gate_state", lambda db, rid: _gate(True))
    assert earn_gate.maybe_queue(_DB(), _review(published=False)) is False
    assert earn_gate.maybe_queue(_DB(), _review(removed=True)) is False


def test_the_seeding_phase_does_not_use_the_gate(monkeypatch):
    monkeypatch.setattr(settings, "earn_gate_phase", "seeding")
    monkeypatch.setattr(earn_gate, "gate_state", lambda db, rid: _gate(True))
    review = _review()
    assert earn_gate.maybe_queue(_DB(), review) is False


def test_new_reviews_start_queued_in_seeding_and_undecided_after(monkeypatch):
    monkeypatch.setattr(settings, "earn_gate_phase", "seeding")
    monkeypatch.setattr(settings, "earn_eligible_auto_queue", True)
    assert earn_gate.initial_status(None) == EarnEligibleStatus.pending
    monkeypatch.setattr(settings, "earn_eligible_auto_queue", False)
    assert earn_gate.initial_status(None) == EarnEligibleStatus.none
    monkeypatch.setattr(settings, "earn_gate_phase", "post_seeding")
    monkeypatch.setattr(settings, "earn_eligible_auto_queue", True)
    assert earn_gate.initial_status(None) == EarnEligibleStatus.none
