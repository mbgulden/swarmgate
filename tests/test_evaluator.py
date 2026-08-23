"""
Unit tests for EscalationEvaluator and Mathematical Scoring Formula.
"""

import pytest
from swarmgate.evaluator import EscalationEvaluator
from swarmgate.policy import GatePolicy
from swarmgate.schemas import AttentionTier, DecisionStatus


def test_tier_1_auto_commit_on_safe_files():
    evaluator = EscalationEvaluator()
    
    # 1. Modifying documentation or markdown file
    d_doc = evaluator.evaluate(
        resource="file:docs/README.md",
        lines_changed=5,
        files_touched=1
    )
    assert d_doc.tier == AttentionTier.TIER_1_AUTO
    assert d_doc.status == DecisionStatus.AUTO_COMMITTED
    assert d_doc.escalation_score < 0.30

    # 2. Modifying a test file
    d_test = evaluator.evaluate(
        resource="file:tests/test_auth.py",
        lines_changed=10,
        files_touched=1
    )
    assert d_test.tier == AttentionTier.TIER_1_AUTO
    assert d_test.escalation_score < 0.30


def test_tier_2_digest_on_standard_logic():
    evaluator = EscalationEvaluator()
    
    # Modifying standard helper logic in utils
    d_utils = evaluator.evaluate(
        resource="file:src/utils/formatting.py",
        lines_changed=30,
        files_touched=2,
        dependents_count=2
    )
    assert d_utils.tier == AttentionTier.TIER_2_DIGEST
    assert 0.30 <= d_utils.escalation_score < 0.70


def test_tier_3_barrier_on_critical_security_paths():
    evaluator = EscalationEvaluator()
    
    # 1. Modifying auth token verification
    d_auth = evaluator.evaluate(
        resource="file:src/auth/jwt.py",
        lines_changed=25,
        files_touched=1,
        dependents_count=5
    )
    assert d_auth.tier == AttentionTier.TIER_3_BARRIER
    assert d_auth.status == DecisionStatus.PENDING
    assert d_auth.escalation_score >= 0.70

    # 2. Modifying .env or credentials
    d_env = evaluator.evaluate(
        resource="file:.env.production",
        lines_changed=2
    )
    assert d_env.tier == AttentionTier.TIER_3_BARRIER
    assert d_env.escalation_score >= 0.70