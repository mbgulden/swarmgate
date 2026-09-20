"""
SwarmLock 2PL Suspension Bridge for SwarmGate.
Coordinates lease freezing (SUSPEND), pending decision storage, and operator resolution.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional

from swarmgate.digest import AsyncDigestManager
from swarmgate.distiller import DecisionDiffDistiller, DistilledCard
from swarmgate.schemas import AttentionTier, DecisionPacket, DecisionStatus

logger = logging.getLogger("swarmgate.bridge")
# Default locations. Both are overridable — see resolve_swarmock_socket_path()
# and PendingDecisionStore.configure() — so embedders (e.g. the Prismatic
# hypervisor) can point the bridge at their own directories instead of these
# unix-leaning defaults.
SWARMLOCK_SOCK = "/tmp/swarmlock.sock"
PENDING_FILE = Path.home() / ".swarmgate" / "pending_decisions.json"

#: Environment variable overriding the swarmlock daemon socket path.
ENV_SWARMLOCK_SOCK = "SWARMGATE_SWARMLOCK_SOCK"
#: Environment variable overriding the pending-decisions file path.
ENV_PENDING_FILE = "SWARMGATE_PENDING_FILE"


def resolve_swarmock_socket_path(socket_path: Optional[str] = None) -> str:
    """Resolve the swarmlock daemon socket path.

    Precedence: explicit argument > ``SWARMGATE_SWARMLOCK_SOCK`` env var >
    the ``SWARMLOCK_SOCK`` module default.
    """
    if socket_path:
        return socket_path
    return os.environ.get(ENV_SWARMLOCK_SOCK) or SWARMLOCK_SOCK


def _resolve_pending_file(explicit: Optional[str | Path] = None) -> Path:
    """Resolve the pending-decisions file path.

    Precedence: explicit argument (incl. PendingDecisionStore.configure()) >
    ``SWARMGATE_PENDING_FILE`` env var > the ``PENDING_FILE`` module default.

    ``PENDING_FILE`` is read dynamically (not captured) so existing callers
    that monkeypatch the module constant keep working.
    """
    if explicit is not None:
        return Path(explicit).expanduser()
    env = os.environ.get(ENV_PENDING_FILE)
    if env:
        return Path(env).expanduser()
    return PENDING_FILE


def send_swarmlock_ipc(payload: Dict[str, Any], socket_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Send a payload to the swarmlock daemon over its unix socket.

    ``socket_path`` overrides the default; when omitted the
    ``SWARMGATE_SWARMLOCK_SOCK`` env var is honored, then the module default.
    Returns None when the daemon is unreachable (fail-open by design).
    """
    resolved = resolve_swarmock_socket_path(socket_path)
    if not os.path.exists(resolved):
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect(resolved)
            client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
            line = client.recv(8192)
            if line:
                return json.loads(line.decode("utf-8").strip())
    except Exception as exc:
        logger.debug("Failed IPC send to swarmlock daemon: %s", exc)
        return None
    return None


class PendingDecisionStore:
    """
    Thread-safe storage for active Tier 3 pending decisions awaiting human operator resolution.

    The backing file defaults to ``~/.swarmgate/pending_decisions.json`` but is
    configurable: call ``PendingDecisionStore.configure(pending_file=...)`` for
    an explicit path, or set the ``SWARMGATE_PENDING_FILE`` env var. The
    module-level ``PENDING_FILE`` constant remains a working override point
    for tests that monkeypatch it.
    """

    _configured_path: Optional[Path] = None

    @classmethod
    def configure(cls, pending_file: Optional[str | Path] = None) -> None:
        """Set (or clear, with None) an explicit pending-decisions file path."""
        cls._configured_path = Path(pending_file).expanduser() if pending_file else None

    @classmethod
    def _path(cls) -> Path:
        return _resolve_pending_file(cls._configured_path)

    @classmethod
    def load_all(cls) -> Dict[str, Dict[str, Any]]:
        path = cls._path()
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @classmethod
    def save_all(cls, data: Dict[str, Dict[str, Any]]) -> None:
        path = cls._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)

    @classmethod
    def add(cls, decision: DecisionPacket, card: DistilledCard) -> None:
        data = cls.load_all()
        d_dict = decision.to_dict()
        d_dict["card"] = {
            "header": card.header,
            "proof_badge": card.proof_badge,
            "compact_diff": card.compact_diff,
            "recommendation": card.recommendation
        }
        data[decision.decision_id] = d_dict
        cls.save_all(data)

    @classmethod
    def get(cls, decision_id: str) -> Optional[Dict[str, Any]]:
        return cls.load_all().get(decision_id)

    @classmethod
    def remove(cls, decision_id: str) -> Optional[Dict[str, Any]]:
        data = cls.load_all()
        popped = data.pop(decision_id, None)
        cls.save_all(data)
        return popped


class SwarmgateBridge:
    """
    Coordinates decision execution across Tier 1, 2, and 3 workflows.
    """

    @classmethod
    def process_decision(
        cls,
        decision: DecisionPacket,
        base_content: Optional[str] = None,
        new_content: Optional[str] = None,
        lock_id: Optional[str] = None,
        tx_id: Optional[str] = None
    ) -> Dict[str, Any]:
        card = DecisionDiffDistiller.distill(decision, base_content, new_content)
        decision.diff_summary = card.compact_diff

        # TIER 1: Autonomous Auto-Commit
        if decision.tier == AttentionTier.TIER_1_AUTO:
            send_swarmlock_ipc({
                "action": "COMMIT",
                "resource": decision.resource,
                "holder": decision.agent_id,
                "lock_id": lock_id,
                "tx_id": tx_id
            })
            return {"status": "AUTO_COMMITTED", "tier": "TIER_1_AUTO", "decision_id": decision.decision_id}

        # TIER 2: Async Digest Auto-Commit
        elif decision.tier == AttentionTier.TIER_2_DIGEST:
            AsyncDigestManager().record(decision)
            send_swarmlock_ipc({
                "action": "COMMIT",
                "resource": decision.resource,
                "holder": decision.agent_id,
                "lock_id": lock_id,
                "tx_id": tx_id
            })
            return {"status": "AUTO_COMMITTED", "tier": "TIER_2_DIGEST", "decision_id": decision.decision_id}

        # TIER 3: Synchronous Push Barrier
        else:
            # 1. Freeze lease TTL in swarmlock
            send_swarmlock_ipc({
                "action": "SUSPEND",
                "resource": decision.resource,
                "holder": decision.agent_id,
                "lock_id": lock_id,
                "tx_id": tx_id
            })
            # 2. Store in pending queue
            PendingDecisionStore.add(decision, card)
            return {
                "status": "SUSPENDED_FOR_REVIEW",
                "tier": "TIER_3_BARRIER",
                "decision_id": decision.decision_id,
                "card_ansi": card.to_terminal_ansi()
            }

    @classmethod
    def resolve_decision(
        cls,
        decision_id: str,
        approved: bool,
        operator: str = "human_operator"
    ) -> bool:
        record = PendingDecisionStore.remove(decision_id)
        if not record:
            return False

        resource = record.get("resource")
        holder = record.get("agent_id")
        lock_id = record.get("metadata", {}).get("lock_id")
        tx_id = record.get("metadata", {}).get("tx_id")

        if approved:
            send_swarmlock_ipc({
                "action": "COMMIT",
                "resource": resource,
                "holder": holder,
                "lock_id": lock_id,
                "tx_id": tx_id
            })
            # Append approved record to digest
            d_pkt = DecisionPacket.from_dict(record)
            d_pkt.status = DecisionStatus.APPROVED
            d_pkt.resolved_by = operator
            AsyncDigestManager().record(d_pkt)
            return True
        else:
            send_swarmlock_ipc({
                "action": "REVERT",
                "resource": resource,
                "holder": holder,
                "lock_id": lock_id,
                "tx_id": tx_id
            })
            return True