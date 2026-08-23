"""
SwarmGate Policy Configuration and Path Weight Matching.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class GatePolicy:
    tier1_max: float = 0.30
    tier2_max: float = 0.70
    max_tier3_per_hour: int = 5
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"

    @classmethod
    def load(cls, policy_path: Optional[str | Path] = None) -> GatePolicy:
        if policy_path is None:
            policy_path = Path.cwd() / ".swarmgate" / "policy.json"
        else:
            policy_path = Path(policy_path)

        if not policy_path.exists():
            return cls()

        try:
            with open(policy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            thresh = data.get("thresholds", {})
            rate = data.get("rate_limits", {})
            return cls(
                tier1_max=thresh.get("tier1_max", 0.30),
                tier2_max=thresh.get("tier2_max", 0.70),
                max_tier3_per_hour=rate.get("max_tier3_per_hour", 5),
                quiet_hours_start=rate.get("quiet_hours_start", "22:00"),
                quiet_hours_end=rate.get("quiet_hours_end", "07:00")
            )
        except Exception:
            return cls()

    def get_path_risk(self, path_str: str) -> float:
        clean = path_str.strip()
        if ":" in clean:
            clean = clean.split(":", 1)[1]
        if "#" in clean:
            clean = clean.split("#", 1)[0]
        clean = clean.replace("\\", "/").lower().strip("/")

        # 1. Tests & docs have safe priority
        if clean.startswith("tests/") or clean.startswith("test_") or "/tests/" in clean or clean.endswith("_test.py"):
            return 0.10
        if clean.startswith("docs/") or clean.endswith(".md"):
            return 0.05

        # 2. Critical credentials & security
        if ".env" in clean or "credential" in clean or "secret" in clean:
            return 1.00
        if "/auth/" in f"/{clean}" or clean.startswith("auth/") or "/security/" in f"/{clean}":
            return 0.95
        if "/migrations/" in f"/{clean}" or clean.endswith(".sql"):
            return 0.90
        if "/engine/" in f"/{clean}" or "/core/" in f"/{clean}":
            return 0.75
        if "/daemon" in f"/{clean}":
            return 0.80
        if "/api/" in f"/{clean}" or "/routes/" in f"/{clean}":
            return 0.65
        if "/utils/" in f"/{clean}" or "/helpers/" in f"/{clean}":
            return 0.50
        return 0.50