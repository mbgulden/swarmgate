"""
Escalation Index (E) Evaluator for SwarmGate.
Deterministically quantifies Blast Radius, Structural Risk, and Reversibility.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from swarmgate.policy import GatePolicy
from swarmgate.schemas import AttentionTier, DecisionPacket, DecisionStatus


class EscalationEvaluator:
    """
    Evaluates mutations using the deterministic Attention Era Escalation formula:
    E = Structural Risk * [0.25 * Blast Radius + 0.75 * (1.0 - 0.30 * Reversibility)]
    """

    def __init__(self, policy: Optional[GatePolicy] = None):
        self.policy = policy or GatePolicy.load()

    def evaluate(
        self,
        resource: str,
        lines_changed: int = 1,
        files_touched: int = 1,
        dependents_count: int = 0,
        reversibility: Optional[float] = None,
        agent_id: str = "default_agent",
        proof_id: Optional[str] = None,
        custom_risk_override: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DecisionPacket:
        reasons: List[str] = []

        # 1. Structural Risk (0.0 to 1.0)
        if custom_risk_override is not None:
            structural_risk = max(0.0, min(custom_risk_override, 1.0))
        else:
            structural_risk = self.policy.get_path_risk(resource)
        reasons.append(f"Structural Risk {structural_risk:.2f} based on target path policy")

        # 2. Blast Radius (0.10 to 1.0)
        line_factor = min(lines_changed / 50.0, 1.0) * 0.40
        file_factor = min(files_touched / 5.0, 1.0) * 0.30
        dep_factor = min(dependents_count / 5.0, 1.0) * 0.30
        blast_radius = max(0.10, min(line_factor + file_factor + dep_factor, 1.0))
        reasons.append(f"Blast Radius {blast_radius:.2f} (lines={lines_changed}, files={files_touched}, deps={dependents_count})")

        # 3. Reversibility (0.0 to 1.0)
        if reversibility is None:
            if structural_risk >= 0.85:
                rev = 0.10
            elif structural_risk <= 0.15:
                rev = 1.00
            else:
                rev = 0.60
        else:
            rev = max(0.0, min(reversibility, 1.0))

        irreversibility_factor = 1.0 - (rev * 0.30)
        reasons.append(f"Reversibility {rev:.2f} (irreversibility factor={irreversibility_factor:.2f})")

        # 4. Calculate Final Escalation Score E
        escalation_score = structural_risk * (0.25 * blast_radius + 0.75 * irreversibility_factor)
        escalation_score = round(max(0.0, min(escalation_score, 1.0)), 3)

        # 5. Classify Attention Tier
        if escalation_score < self.policy.tier1_max:
            tier = AttentionTier.TIER_1_AUTO
            status = DecisionStatus.AUTO_COMMITTED
            reasons.append(f"Classified TIER_1_AUTO (E={escalation_score} < {self.policy.tier1_max})")
        elif escalation_score < self.policy.tier2_max:
            tier = AttentionTier.TIER_2_DIGEST
            status = DecisionStatus.AUTO_COMMITTED
            reasons.append(f"Classified TIER_2_DIGEST ({self.policy.tier1_max} <= E={escalation_score} < {self.policy.tier2_max})")
        else:
            tier = AttentionTier.TIER_3_BARRIER
            status = DecisionStatus.PENDING
            reasons.append(f"Classified TIER_3_BARRIER (E={escalation_score} >= {self.policy.tier2_max}) -> Human Approval Required")

        decision_id = f"dec_{uuid.uuid4().hex[:16]}"
        return DecisionPacket(
            decision_id=decision_id,
            resource=resource,
            agent_id=agent_id,
            escalation_score=escalation_score,
            tier=tier,
            blast_radius=round(blast_radius, 3),
            structural_risk=round(structural_risk, 3),
            reversibility=round(rev, 3),
            reasons=reasons,
            proof_id=proof_id,
            status=status,
            metadata=metadata or {}
        )