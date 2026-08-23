"""
SwarmGate Command Line Interface (CLI).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from swarmgate.bridge import PendingDecisionStore, SwarmgateBridge
from swarmgate.digest import AsyncDigestManager
from swarmgate.distiller import DecisionDiffDistiller
from swarmgate.evaluator import EscalationEvaluator
from swarmgate.policy import GatePolicy
from swarmgate.schemas import AttentionTier
from swarmgate.server import run_server


def cmd_evaluate(args: argparse.Namespace) -> int:
    raw_path = args.file.strip()
    clean_path = raw_path[5:] if raw_path.startswith("file:") else raw_path
    target_path = Path(clean_path)
    evaluator = EscalationEvaluator()

    content = None
    lines_changed = args.lines
    if target_path.exists():
        content = target_path.read_text(encoding="utf-8", errors="replace")
        if lines_changed is None:
            lines_changed = len(content.splitlines())
    elif lines_changed is None:
        lines_changed = 10

    decision = evaluator.evaluate(
        resource=f"file:{clean_path}",
        lines_changed=lines_changed,
        files_touched=args.files or 1,
        dependents_count=args.deps or 0,
        reversibility=args.rev,
        agent_id=args.agent or "default_agent",
        proof_id=args.proof
    )

    result = SwarmgateBridge.process_decision(
        decision=decision,
        new_content=content,
        lock_id=args.lock_id,
        tx_id=args.tx_id
    )

    if args.json:
        out = decision.to_dict()
        out["bridge_action"] = result.get("status")
        print(json.dumps(out, indent=2))
    else:
        card = DecisionDiffDistiller.distill(decision, new_content=content)
        print(card.to_terminal_ansi())

    if decision.tier == AttentionTier.TIER_3_BARRIER:
        return 2
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    mgr = AsyncDigestManager()
    if args.clear:
        mgr.clear()
        print("🟢 SwarmGate digest cleared.")
        return 0

    since = None
    if args.since:
        now = time.time()
        if args.since.endswith("h"):
            since = now - float(args.since[:-1]) * 3600
        elif args.since.endswith("d"):
            since = now - float(args.since[:-1]) * 86400

    entries = mgr.get_entries(since_timestamp=since)
    print("=" * 72)
    print(f" 📋 SWARMGATE ASYNC DIGEST  ({len(entries)} auto-committed mutations)")
    print("=" * 72)
    if not entries:
        print("  (No digest entries recorded in this window)")
    else:
        print(f"  {'DECISION':<18} {'RESOURCE':<28} {'SCORE':<8} {'STATUS':<12}")
        print("  " + "-" * 68)
        for e in entries:
            print(f"  {e['decision_id']:<18} {e['resource']:<28} E={e['escalation_score']:<5} {e['status']:<12}")
    print("=" * 72)
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    pending = PendingDecisionStore.load_all()
    if not pending:
        print("🟢 No decisions pending review. All clear!")
        return 0

    print("=" * 72)
    print(f" 🚦 SWARMGATE INTERACTIVE REVIEW QUEUE ({len(pending)} pending)")
    print("=" * 72)

    for dec_id, d in list(pending.items()):
        print(f"\nDecision ID:    {dec_id}")
        print(f"Resource:       {d['resource']}")
        print(f"Agent:          {d['agent_id']}")
        print(f"Risk Score:     E={d['escalation_score']} ({d['tier']})")
        print(f"Proof:          {d.get('card', {}).get('proof_badge', 'None')}")
        print("\nDiff:")
        print(d.get("card", {}).get("compact_diff", "(No diff)"))

        if args.non_interactive:
            continue

        choice = input("\n[y] Approve & Commit | [n] Reject & Revert | [s] Skip: ").strip().lower()
        if choice == "y":
            SwarmgateBridge.resolve_decision(dec_id, approved=True)
            print(f"✅ Approved {dec_id}")
        elif choice == "n":
            SwarmgateBridge.resolve_decision(dec_id, approved=False)
            print(f"❌ Rejected {dec_id}")
        else:
            print(f"⏭️ Skipped {dec_id}")

    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    run_server(host=args.host, port=args.port)
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    approved = (args.action == "approve")
    ok = SwarmgateBridge.resolve_decision(args.decision_id, approved=approved)
    if ok:
        print(f"{'✅ Approved' if approved else '❌ Rejected'} decision '{args.decision_id}'")
        return 0
    else:
        print(f"Error: Decision '{args.decision_id}' not found")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="swarmgate",
        description="SwarmGate: Attention Governor & Escalation Hypervisor",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Evaluate code change and route to Tier 1, 2, or 3")
    p_eval.add_argument("file", help="Target file path")
    p_eval.add_argument("--proof", help="SwarmProof Proof ID")
    p_eval.add_argument("--lines", type=int, default=None, help="Lines changed")
    p_eval.add_argument("--files", type=int, default=1, help="Files touched in batch")
    p_eval.add_argument("--deps", type=int, default=0, help="Downstream dependents")
    p_eval.add_argument("--rev", type=float, default=None, help="Reversibility (0.0 to 1.0)")
    p_eval.add_argument("--agent", default="default_agent", help="Agent identifier")
    p_eval.add_argument("--lock-id", default=None, help="Swarmlock Lease ID")
    p_eval.add_argument("--tx-id", default=None, help="SwarmSaga Transaction ID")
    p_eval.add_argument("--json", action="store_true", help="Output JSON packet")
    p_eval.set_defaults(func=cmd_evaluate)

    # digest
    p_dig = sub.add_parser("digest", help="View or clear async digest log")
    p_dig.add_argument("--since", help="Filter by time window (e.g. 1h, 24h, 7d)")
    p_dig.add_argument("--clear", action="store_true", help="Clear digest log")
    p_dig.set_defaults(func=cmd_digest)

    # review
    p_rev = sub.add_parser("review", help="Interactive terminal review of pending Tier 3 decisions")
    p_rev.add_argument("--non-interactive", action="store_true", help="Print pending queue without prompt")
    p_rev.set_defaults(func=cmd_review)

    # serve
    p_srv = sub.add_parser("serve", help="Run mobile Tailscale HTTP review server")
    p_srv.add_argument("--port", type=int, default=8999, help="Port (default: 8999)")
    p_srv.add_argument("--host", default=None, help="Host to bind (default: Tailscale IP)")
    p_srv.set_defaults(func=cmd_serve)

    # approve / reject
    p_app = sub.add_parser("approve", help="Approve a pending Tier 3 decision")
    p_app.add_argument("decision_id", help="Decision ID")
    p_app.set_defaults(func=cmd_resolve, action="approve")

    p_rej = sub.add_parser("reject", help="Reject a pending Tier 3 decision")
    p_rej.add_argument("decision_id", help="Decision ID")
    p_rej.set_defaults(func=cmd_resolve, action="reject")

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()