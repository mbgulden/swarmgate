"""
Unit tests for SwarmgateBridge and PendingDecisionStore.
"""

import tempfile
from pathlib import Path
from swarmgate.bridge import PendingDecisionStore, SwarmgateBridge
from swarmgate.evaluator import EscalationEvaluator
from swarmgate.schemas import AttentionTier


def test_bridge_tier_routing_and_resolution():
    evaluator = EscalationEvaluator()

    # Tier 1 auto-commit
    d_safe = evaluator.evaluate("file:docs/README.md", lines_changed=2)
    res_safe = SwarmgateBridge.process_decision(d_safe)
    assert res_safe["status"] == "AUTO_COMMITTED"

    # Tier 3 barrier suspension
    d_crit = evaluator.evaluate("file:src/auth/jwt.py", lines_changed=30)
    res_crit = SwarmgateBridge.process_decision(d_crit)
    assert res_crit["status"] == "SUSPENDED_FOR_REVIEW"
    dec_id = d_crit.decision_id

    # Verify present in pending store
    record = PendingDecisionStore.get(dec_id)
    assert record is not None
    assert record["resource"] == "file:src/auth/jwt.py"

    # Approve decision
    ok = SwarmgateBridge.resolve_decision(dec_id, approved=True)
    assert ok is True

    # After approval, must be cleared from pending
    assert PendingDecisionStore.get(dec_id) is None