"""
Unit tests for DecisionDiffDistiller.
"""

from swarmgate.distiller import DecisionDiffDistiller
from swarmgate.evaluator import EscalationEvaluator


def test_diff_distillation_and_truncation():
    evaluator = EscalationEvaluator()
    decision = evaluator.evaluate("file:src/auth/jwt.py", lines_changed=20, proof_id="prf_test123")

    base = "def authenticate():\n    return False\n"
    new = "def authenticate():\n    check_mfa()\n    return True\n"

    card = DecisionDiffDistiller.distill(decision, base_content=base, new_content=new)
    assert "jwt.py" in card.resource
    assert "prf_test123" in card.proof_badge
    assert "+    check_mfa()" in card.compact_diff
    assert "SWARMGATE ATTENTION CARD" in card.to_terminal_ansi()