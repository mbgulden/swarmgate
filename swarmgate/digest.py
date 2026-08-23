"""
Async Digest Manager for SwarmGate.
Maintains an append-only JSONL log of non-blocking Tier 2 mutations for periodic operator review.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from swarmgate.schemas import DecisionPacket


class AsyncDigestManager:
    """
    Manages non-blocking audit logging for Tier 2 decisions.
    """

    def __init__(self, digest_file: Optional[str | Path] = None):
        if digest_file is None:
            base_dir = Path.home() / ".swarmgate"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.digest_file = base_dir / "digest.jsonl"
        else:
            self.digest_file = Path(digest_file)
            self.digest_file.parent.mkdir(parents=True, exist_ok=True)

    def record(self, decision: DecisionPacket) -> None:
        """Append decision packet to JSONL digest log."""
        line = json.dumps(decision.to_dict()) + "\n"
        with open(self.digest_file, "a", encoding="utf-8") as f:
            f.write(line)

    def get_entries(
        self,
        since_timestamp: Optional[float] = None,
        tier: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve digest entries filtered by timestamp or tier."""
        if not self.digest_file.exists():
            return []

        entries = []
        with open(self.digest_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line.strip())
                    if since_timestamp and data.get("timestamp", 0) < since_timestamp:
                        continue
                    if tier and data.get("tier") != tier:
                        continue
                    entries.append(data)
                except Exception:
                    continue
        return entries

    def clear(self) -> None:
        """Clear or rotate digest log."""
        if self.digest_file.exists():
            self.digest_file.unlink()