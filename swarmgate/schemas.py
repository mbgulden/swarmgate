"""
SwarmGate Core Schemas and Data Models.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AttentionTier(str, Enum):
    TIER_1_AUTO = "TIER_1_AUTO"        # E < 0.30: Autonomous auto-commit
    TIER_2_DIGEST = "TIER_2_DIGEST"    # 0.30 <= E < 0.70: Auto-commit + append to async review digest
    TIER_3_BARRIER = "TIER_3_BARRIER"  # E >= 0.70: Synchronous human approval barrier (swarmlock SUSPEND)


class DecisionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AUTO_COMMITTED = "AUTO_COMMITTED"
    TIMED_OUT = "TIMED_OUT"


@dataclass
class DecisionPacket:
    decision_id: str
    resource: str
    agent_id: str
    escalation_score: float
    tier: AttentionTier
    blast_radius: float
    structural_risk: float
    reversibility: float
    reasons: List[str]
    proof_id: Optional[str] = None
    status: DecisionStatus = DecisionStatus.PENDING
    diff_summary: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tier"] = self.tier.value
        d["status"] = self.status.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DecisionPacket:
        tier = AttentionTier(data["tier"])
        status = DecisionStatus(data.get("status", DecisionStatus.PENDING.value))
        return cls(
            decision_id=data["decision_id"],
            resource=data["resource"],
            agent_id=data["agent_id"],
            escalation_score=float(data["escalation_score"]),
            tier=tier,
            blast_radius=float(data.get("blast_radius", 0.0)),
            structural_risk=float(data.get("structural_risk", 0.0)),
            reversibility=float(data.get("reversibility", 1.0)),
            reasons=data.get("reasons", []),
            proof_id=data.get("proof_id"),
            status=status,
            diff_summary=data.get("diff_summary"),
            timestamp=float(data.get("timestamp", time.time())),
            resolved_at=data.get("resolved_at"),
            resolved_by=data.get("resolved_by"),
            metadata=data.get("metadata", {})
        )