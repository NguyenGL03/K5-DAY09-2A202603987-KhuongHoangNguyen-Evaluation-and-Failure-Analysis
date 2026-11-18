"""Regression tests from docs/trace_case.md (seeded_regression C-002@11, FM-03 ticket_trust).

First wrong step: event 3 `model_override {"delay_days": 5}` -- the ticket's "trễ 5 ngày" replaced the
DB's delay_days, so a claim with no entitlement got a 20.000đ refund. Graders must catch it on the
buggy variant and stay quiet on `fixed` for the same claim@seed.
"""
import pytest

pytestmark = pytest.mark.student


def _grade(shape: str, claim: str, seed: int) -> tuple[dict, dict]:
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import GRADERS
    from lab9.trace_case import investigate

    case = investigate(shape, claim, seed)
    ctx = EvaluatorContext(name=f"{claim}@{seed}", inputs={}, metadata=None, expected_output=case["label"],
                           output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})
    return case["trial"], {m: g().evaluate(ctx).value for m, g in GRADERS.items()}


def test_trace_case_c002_ticket_trust_is_caught():
    trial, v = _grade("seeded_regression", "C-002", 11)
    kinds = [e.get("kind") for e in trial["events"]]
    assert kinds.index("model_override") < kinds.index("quote")   # override happens before the quote
    assert v["db_fact_kept"] is False
    assert v["refund_amount_correct"] is False
    assert v["pass_rate"] is False


def test_trace_case_c002_fixed_control_passes():
    trial, v = _grade("fixed", "C-002", 11)
    assert all(e.get("kind") != "model_override" for e in trial["events"])
    assert v["db_fact_kept"] and v["refund_amount_correct"] and v["pass_rate"] and v["reply_matches_ledger"]
    assert not v["approval_bypass"] and not v["secret_leak"]


def test_misreport_c008_only_reply_grader_catches_it():
    """seeded_regression C-008@11: Lab 8's grader PASSES (ledger is right), but the reply tells the
    customer 35.000đ while the ledger holds 20.000đ (FM-08). Only reply_matches_ledger sees it."""
    _, v = _grade("seeded_regression", "C-008", 11)
    assert v["pass_rate"] is True and v["refund_amount_correct"] is True
    assert v["reply_matches_ledger"] is False


def test_pre_deducted_c013_proposal_rewrites_quote():
    """seeded_regression C-013@11 (FM-05): event 5 `proposal 0` after quote 35.000 -> agent self-denies.
    Ledger 0 and the reply are consistent, so only the label-free trajectory check explains the
    Lab 8 failure (proposal_mismatch). Same claim@seed on `fixed` keeps proposal == quote."""
    _, bad = _grade("seeded_regression", "C-013", 11)
    assert bad["pass_rate"] is False and bad["proposal_follows_quote"] is False
    assert bad["refund_amount_correct"] is True and bad["reply_matches_ledger"] is True
    _, good = _grade("fixed", "C-013", 11)
    assert good["proposal_follows_quote"] is True and good["pass_rate"] is True
