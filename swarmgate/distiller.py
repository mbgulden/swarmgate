"""
Decision Diff Distiller for SwarmGate.
Compresses raw AST diffs into concise, human-scannable executive decision cards.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from swarmgate.schemas import DecisionPacket


@dataclass
class DistilledCard:
    header: str
    decision_id: str
    resource: str
    agent_id: str
    tier: str
    escalation_score: float
    proof_badge: str
    compact_diff: str
    recommendation: str

    def to_terminal_ansi(self) -> str:
        border = "=" * 68
        lines = [
            border,
            f" 🚦 SWARMGATE ATTENTION CARD  |  Decision: {self.decision_id}",
            border,
            f"  Resource:       {self.resource}",
            f"  Agent:          {self.agent_id}",
            f"  Attention Tier: {self.tier} (Score: {self.escalation_score})",
            f"  Proof Badge:    {self.proof_badge}",
            f"  Recommendation: {self.recommendation}",
            "-" * 68,
            "  Compact Contextual Diff:",
        ]
        for line in self.compact_diff.splitlines():
            lines.append(f"    {line}")
        lines.append(border)
        return "\n".join(lines)


class DecisionDiffDistiller:
    """
    Distills code changes into executive decision summaries.
    """

    @staticmethod
    def generate_compact_diff(
        base_content: Optional[str],
        new_content: Optional[str],
        max_lines: int = 15
    ) -> str:
        base_lines = (base_content or "").splitlines(keepends=True)
        new_lines = (new_content or "").splitlines(keepends=True)

        diff = list(difflib.unified_diff(base_lines, new_lines, n=2))
        if not diff:
            return "(No content modifications)"

        clean_diff = [l.rstrip("\r\n") for l in diff[2:]]  # Skip header
        if len(clean_diff) > max_lines:
            truncated = clean_diff[:max_lines]
            truncated.append(f"... ({len(clean_diff) - max_lines} more lines omitted)")
            return "\n".join(truncated)
        return "\n".join(clean_diff)

    @classmethod
    def distill(
        cls,
        decision: DecisionPacket,
        base_content: Optional[str] = None,
        new_content: Optional[str] = None
    ) -> DistilledCard:
        compact_diff = cls.generate_compact_diff(base_content, new_content)
        proof_badge = f"🛡️ VERIFIED [{decision.proof_id}]" if decision.proof_id else "⚪ UNVERIFIED"

        if decision.tier.value == "TIER_1_AUTO":
            recom = "Autonomous auto-commit. No operator action required."
        elif decision.tier.value == "TIER_2_DIGEST":
            recom = "Auto-committed to async digest. Review during batch window."
        else:
            recom = "🛑 HIGH BLAST RADIUS / CRITICAL PATH. Human approval required."

        return DistilledCard(
            header="SWARMGATE DECISION CARD",
            decision_id=decision.decision_id,
            resource=decision.resource,
            agent_id=decision.agent_id,
            tier=decision.tier.value,
            escalation_score=decision.escalation_score,
            proof_badge=proof_badge,
            compact_diff=compact_diff,
            recommendation=recom
        )