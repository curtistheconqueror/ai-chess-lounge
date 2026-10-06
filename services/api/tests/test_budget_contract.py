import multiprocessing
from concurrent.futures import ProcessPoolExecutor

import pytest
from budget_ledger_fixture import ContractConflict, LedgerFixture, reserve_from_process


def test_independent_processes_cannot_oversubscribe_symbolic_budget(tmp_path):
    path = tmp_path / "generated-ledger.db"
    ledger = LedgerFixture(path, limit=10)
    with ProcessPoolExecutor(
        max_workers=4, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        results = list(pool.map(reserve_from_process, [str(path)] * 8, range(8)))
    assert results.count("reserved") == 3
    assert ledger.snapshot()["available"] == 1
    assert ledger.snapshot()["transitions"] == 3


def test_symbolic_uncertain_hold_survives_reopen_and_recovery(tmp_path):
    path = tmp_path / "generated-ledger.db"
    ledger = LedgerFixture(path)
    assert ledger.reserve("original", 7) == "reserved"
    ledger.transition("original", "in_flight")
    reopened = LedgerFixture(path)
    reopened.recover(fenced_sender_proof="fixture sender fenced")
    assert reopened.snapshot()["states"]["original"] == "uncertain"
    assert reopened.snapshot()["available"] == 3
    with pytest.raises(ContractConflict):
        reopened.transition("original", "released", unsent_proof="fixture never dispatched")
    assert reopened.reserve("explicit-new-retry", 7) is None
    # Late fixture evidence settles the original attempt; no chess commit is exercised.
    reopened.transition(
        "original", "reconciled", amount=5, evidence_source="fixture-statement", evidence="bill-1"
    )
    assert reopened.snapshot()["available"] == 5


def test_idempotency_changed_parameters_and_unknown_vs_zero(tmp_path):
    ledger = LedgerFixture(tmp_path / "generated-ledger.db")
    ledger.reserve("call", 4)
    assert ledger.reserve("call", 4) == "reserved"
    with pytest.raises(ContractConflict):
        ledger.reserve("call", 5)
    ledger.transition("call", "in_flight")
    with pytest.raises(ContractConflict):
        ledger.transition(
            "call",
            "reconciled",
            amount=None,
            evidence_source="fixture-statement",
            evidence="unknown",
        )
    assert ledger.snapshot()["available"] == 6
    ledger.transition(
        "call", "reconciled", amount=0, evidence_source="fixture-statement", evidence="proven-zero"
    )
    ledger.transition(
        "call", "reconciled", amount=0, evidence_source="fixture-statement", evidence="proven-zero"
    )
    assert ledger.snapshot()["available"] == 10
    assert ledger.snapshot()["transitions"] == 3
    with pytest.raises(ContractConflict):
        ledger.transition(
            "call",
            "reconciled",
            amount=1,
            evidence_source="fixture-statement",
            evidence="proven-zero",
        )


def test_reconciliation_evidence_unique_and_overage_not_truncated(tmp_path):
    ledger = LedgerFixture(tmp_path / "generated-ledger.db")
    for call in ("a", "b"):
        ledger.reserve(call, 2)
        ledger.transition(call, "in_flight")
    ledger.transition(
        "a", "reconciled", amount=12, evidence_source="fixture-statement", evidence="bill"
    )
    with pytest.raises(ContractConflict):
        ledger.transition(
            "b", "reconciled", amount=1, evidence_source="fixture-statement", evidence="bill"
        )
    assert ledger.snapshot()["states"]["b"] == "in_flight"
    assert ledger.snapshot()["available"] == -4
    assert ledger.reserve("c", 1) is None


def test_cancel_can_release_only_proven_unsent_reservation(tmp_path):
    ledger = LedgerFixture(tmp_path / "generated-ledger.db")
    ledger.reserve("unsent", 3)
    ledger.transition("unsent", "released", unsent_proof="fixture never dispatched")
    ledger.transition("unsent", "released", unsent_proof="fixture never dispatched")
    assert ledger.snapshot()["available"] == 10
    assert ledger.reserve("unsent", 3) == "released"
    with pytest.raises(ContractConflict):
        ledger.transition("unsent", "in_flight")


@pytest.mark.parametrize("attempt", [None, "", " ", 12, "x" * 129])
def test_invalid_attempt_ids_cannot_bypass_idempotency(tmp_path, attempt):
    ledger = LedgerFixture(tmp_path / "generated-ledger.db")
    with pytest.raises(ValueError):
        ledger.reserve(attempt, 3)
    assert ledger.snapshot()["available"] == 10
    assert ledger.snapshot()["transitions"] == 0


def test_multiple_billing_lines_from_same_source_and_policy_immutability(tmp_path):
    path = tmp_path / "generated-ledger.db"
    ledger = LedgerFixture(path)
    for call, line in [("a", "line1"), ("b", "line2")]:
        ledger.reserve(call, 2)
        ledger.transition(call, "in_flight")
        ledger.transition(call, "reconciled", amount=1, evidence_source="statement", evidence=line)
    assert ledger.snapshot()["available"] == 8
    with pytest.raises(ContractConflict, match="immutable"):
        LedgerFixture(path, limit=11)
    with pytest.raises(ContractConflict, match="unsent-proof"):
        ledger.transition("a", "released")


def test_duplicate_attempt_id_racing_processes_has_one_hold(tmp_path):
    path = tmp_path / "generated-ledger.db"
    ledger = LedgerFixture(path)
    with ProcessPoolExecutor(
        max_workers=4, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        results = list(pool.map(reserve_from_process, [str(path)] * 8, ["same"] * 8))
    assert results == ["reserved"] * 8
    assert ledger.snapshot()["available"] == 7
    assert ledger.snapshot()["transitions"] == 1
