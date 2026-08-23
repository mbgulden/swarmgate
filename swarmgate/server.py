from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from swarmgate.bridge import PendingDecisionStore, SwarmgateBridge

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_tailscale_ip() -> str:
    try:
        res = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2.0)
        if res.returncode == 0:
            ip = res.stdout.strip().splitlines()[0].strip()
            if ip.startswith("100."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Prismatic Agent Hypervisor Cockpit</title>
<style>
  :root {
    --bg: #090d13;
    --card: #161b22;
    --card-hover: #1c2128;
    --border: #30363d;
    --text: #c9d1d9;
    --text-muted: #8b949e;
    --text-bright: #ffffff;
    --accent: #58a6ff;
    --green: #238636;
    --green-bg: #23863622;
    --red: #da3633;
    --red-bg: #da363322;
    --warn: #d29922;
    --warn-bg: #d2992222;
    --purple: #bc8cff;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 16px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text); -webkit-font-smoothing: antialiased;
    max-width: 900px; margin: 0 auto;
  }
  header {
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;
    padding-bottom: 12px; border-bottom: 1px solid var(--border);
  }
  h1 { font-size: 1.25rem; margin: 0; display: flex; align-items: center; gap: 8px; color: var(--text-bright); }
  .badge { background: #388bfd26; color: var(--accent); padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: bold; }
  
  .nav-tabs { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 8px; overflow-x: auto; }
  .tab-btn {
    background: transparent; border: 1px solid transparent; color: var(--text-muted); padding: 8px 14px;
    border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: all 0.2s; white-space: nowrap;
  }
  .tab-btn.active { background: var(--card); border-color: var(--border); color: var(--accent); }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; }

  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 18px; margin-bottom: 16px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  }
  .card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; gap: 10px; }
  .resource-title { font-family: "SF Mono", Consolas, monospace; font-size: 0.95rem; font-weight: bold; color: var(--text-bright); word-break: break-all; }
  .score-badge { padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; white-space: nowrap; }
  .badge-tier3 { background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }
  .badge-tier2 { background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn); }
  
  .meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; margin-bottom: 14px; font-size: 0.8rem; color: var(--text-muted); }
  .meta-item b { color: var(--text); }
  
  .intent-box {
    background: #121820; border-left: 3px solid var(--accent); padding: 10px 14px; border-radius: 0 8px 8px 0;
    margin-bottom: 12px; font-size: 0.85rem; color: #e6edf3;
  }
  .risk-box {
    background: var(--red-bg); border-left: 3px solid var(--red); padding: 10px 14px; border-radius: 0 8px 8px 0;
    margin-bottom: 12px; font-size: 0.85rem; color: #ff7b72;
  }
  .comp-box {
    background: var(--green-bg); border-left: 3px solid var(--green); padding: 10px 14px; border-radius: 0 8px 8px 0;
    margin-bottom: 12px; font-size: 0.85rem; color: #7ee787;
  }

  .diff-container {
    background: #06090f; border: 1px solid #21262d; border-radius: 8px; padding: 12px; font-size: 0.8rem;
    overflow-x: auto; color: #e6edf3; font-family: "SF Mono", Consolas, monospace; line-height: 1.45; max-height: 280px;
  }
  .diff-line-add { color: #7ee787; background: #033a1644; }
  .diff-line-del { color: #ff7b72; background: #67060c44; }
  
  .btn-group { display: flex; gap: 12px; margin-top: 16px; }
  button.action-btn {
    flex: 1; padding: 12px; border-radius: 8px; border: none; font-weight: bold; font-size: 0.95rem; cursor: pointer;
    transition: opacity 0.2s;
  }
  button.action-btn:active { opacity: 0.7; }
  .btn-approve { background: var(--green); color: #fff; }
  .btn-reject { background: var(--red); color: #fff; }
  .btn-secondary { background: #21262d; color: var(--text); border: 1px solid var(--border); font-size: 0.8rem; padding: 6px 12px; }

  .empty-state { text-align: center; padding: 48px 20px; color: var(--text-muted); }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); }
  th { color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; }
</style>
</head>
<body>

<header>
  <h1>⚡ Prismatic Hypervisor Cockpit</h1>
  <span class="badge" id="host-badge">Standalone</span>
</header>

<div class="nav-tabs">
  <button class="tab-btn active" onclick="switchTab('attention')">🚦 Attention Barrier (<span id="count-attention">0</span>)</button>
  <button class="tab-btn" onclick="switchTab('sagas')">📦 Sagas & DLQ</button>
  <button class="tab-btn" onclick="switchTab('locks')">🔒 Active Locks</button>
  <button class="tab-btn" onclick="switchTab('ledger')">📜 Merkle Provenance</button>
</div>

<!-- TAB 1: ATTENTION REVIEW -->
<div id="tab-attention" class="tab-pane active">
  <div id="decisions-container"></div>
</div>

<!-- TAB 2: SAGAS & DLQ -->
<div id="tab-sagas" class="tab-pane">
  <div class="card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <h3 style="margin:0;">📦 Quarantined Sagas & Dead-Letter Queue</h3>
      <button class="btn-secondary" onclick="triggerGC()">🧹 Reclaim Stale Worktrees (GC)</button>
    </div>
    <div id="sagas-container">
      <div class="empty-state"><p>No active or quarantined sagas in local journal.</p></div>
    </div>
  </div>
</div>

<!-- TAB 3: LOCKS -->
<div id="tab-locks" class="tab-pane">
  <div class="card">
    <h3 style="margin:0 0 12px 0;">🔒 Active MVCC Resource Leases</h3>
    <div id="locks-container">
      <div class="empty-state"><p>No active locks held in concurrency arbiter.</p></div>
    </div>
  </div>
</div>

<!-- TAB 4: MERKLE LEDGER -->
<div id="tab-ledger" class="tab-pane">
  <div class="card">
    <h3 style="margin:0 0 12px 0;">📜 Causal Provenance DAG</h3>
    <div id="ledger-container">
      <div class="empty-state"><p>No Merkle nodes recorded yet in current span.</p></div>
    </div>
  </div>
</div>

<script>
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-' + tabId).classList.add('active');
}

function renderDiff(diffText) {
  if (!diffText) return '<div style="color:var(--text-muted); font-style:italic;">(No concrete diff modifications)</div>';
  return diffText.split('\\n').map(line => {
    if (line.startsWith('+') && !line.startsWith('+++')) return `<div class="diff-line-add">${escapeHtml(line)}</div>`;
    if (line.startsWith('-') && !line.startsWith('---')) return `<div class="diff-line-del">${escapeHtml(line)}</div>`;
    return `<div>${escapeHtml(line)}</div>`;
  }).join('');
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function loadDecisions() {
  try {
    const res = await fetch('/api/decisions');
    const data = await res.json();
    const container = document.getElementById('decisions-container');
    const keys = Object.keys(data);
    document.getElementById('count-attention').innerText = keys.length;

    if (keys.length === 0) {
      container.innerHTML = `
        <div class="card empty-state">
          <h3>🟢 All Systems Clear</h3>
          <p>No high-risk operations currently suspended. Agents executing freely.</p>
        </div>`;
      return;
    }

    container.innerHTML = keys.map(id => {
      const d = data[id];
      const taskLabel = d.task_id ? `<a href="#" style="color:var(--accent); text-decoration:none;">[${escapeHtml(d.task_id)}]</a> ${escapeHtml(d.task_title || '')}` : 'Ad-Hoc Agent Mutation';
      const intentHtml = d.agent_intent ? `<div class="intent-box"><b>Agent Intent:</b> ${escapeHtml(d.agent_intent)}</div>` : '';
      const riskHtml = d.plain_english_risk ? `<div class="risk-box"><b>Risk Breakdown:</b> ${escapeHtml(d.plain_english_risk)}</div>` : '';
      const compHtml = d.compensation_plan ? `<div class="comp-box"><b>Automatic Rollback Action:</b> ${escapeHtml(d.compensation_plan)}</div>` : '';
      const diffContent = d.unified_diff || (d.card ? d.card.compact_diff : '');

      return `
        <div class="card" id="card-${id}">
          <div class="card-header">
            <div>
              <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:4px;">${taskLabel}</div>
              <div class="resource-title">${escapeHtml(d.resource)}</div>
            </div>
            <span class="score-badge badge-tier3">Barrier E=${d.escalation_score}</span>
          </div>

          <div class="meta-grid">
            <div class="meta-item">Agent: <b>${escapeHtml(d.agent_id)}</b></div>
            <div class="meta-item">Proof Status: <b>${d.proof_id ? '✓ Sealed (' + d.proof_id.slice(0,10) + ')' : 'Pending'}</b></div>
            <div class="meta-item">Blast Radius: <b>${d.blast_radius || 0.5}</b></div>
            <div class="meta-item">Reversibility: <b>${d.reversibility || 0.0}</b></div>
          </div>

          ${intentHtml}
          ${riskHtml}
          ${compHtml}

          <div class="diff-container">
            ${renderDiff(diffContent)}
          </div>

          <div class="btn-group">
            <button class="action-btn btn-approve" onclick="resolve('${id}', true)">✓ Approve & Commit</button>
            <button class="action-btn btn-reject" onclick="resolve('${id}', false)">✗ Reject & Rollback</button>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    console.error("Failed loading decisions", e);
  }
}

async function resolve(id, approved) {
  const el = document.getElementById('card-' + id);
  if (el) el.style.opacity = '0.3';
  await fetch(`/api/decisions/${id}/${approved ? 'approve' : 'reject'}`, { method: 'POST' });
  loadDecisions();
}

async function triggerGC() {
  const res = await fetch('/api/sagas/gc', { method: 'POST' });
  const data = await res.json();
  alert(`Garbage Collection Complete: Reclaimed ${data.cleaned_count} worktrees.`);
}

loadDecisions();
setInterval(loadDecisions, 2500);
</script>
</body>
</html>
"""


class SwarmgateHTTPHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

        elif parsed.path == "/api/decisions":
            decisions = PendingDecisionStore.load_all()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(decisions).encode("utf-8"))

        elif parsed.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ONLINE", "port": 8999}).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.strip("/").split("/") if p]

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decisions":
            decision_id = parts[2]
            action = parts[3]
            approved = action == "approve"
            success = SwarmgateBridge.resolve_decision(decision_id, approved=approved)
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "decision_id": decision_id, "approved": approved}).encode("utf-8"))

        elif len(parts) == 3 and parts[0] == "api" and parts[1] == "sagas" and parts[2] == "gc":
            try:
                from swarmsaga.journal.engine import JournalEngine
                from swarmsaga.workspace.gc import SagaGarbageCollector
                gc = SagaGarbageCollector(journal=JournalEngine())
                cleaned = gc.sweep_stale_worktrees()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "SUCCESS", "cleaned_count": len(cleaned), "cleaned": cleaned}).encode("utf-8"))
            except Exception as exc:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()


def run_server(port: int = 8999, host: str = "0.0.0.0"):
    server = HTTPServer((host, port), SwarmgateHTTPHandler)
    tailscale_ip = get_tailscale_ip()
    print("Prismatic Hypervisor Cockpit live at:")
    print(f"   • Local:     http://127.0.0.1:{port}")
    if tailscale_ip != "127.0.0.1":
        print(f"   • Tailscale: http://{tailscale_ip}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Hypervisor Cockpit...")
        server.server_close()


if __name__ == "__main__":
    run_server()