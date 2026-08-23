"""
Lightweight Mobile Web Review Server for SwarmGate.
Serves a responsive 1-tap mobile card UI over Tailscale on port 8999.
"""

from __future__ import annotations

import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from swarmgate.bridge import PendingDecisionStore, SwarmgateBridge


def get_tailscale_ip() -> str:
    try:
        res = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2.0)
        if res.returncode == 0:
            ip = res.stdout.strip().splitlines()[0].strip()
            if ip.startswith("100."):
                return ip
    except Exception:
        pass
    return "0.0.0.0"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>SwarmGate Attention Review</title>
<style>
  :root {
    --bg: #0d1117;
    --card: #161b22;
    --border: #30363d;
    --text: #c9d1d9;
    --accent: #58a6ff;
    --green: #238636;
    --red: #da3633;
    --warn: #d29922;
  }
  body {
    margin: 0; padding: 16px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text); -webkit-font-smoothing: antialiased;
  }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
  h1 { font-size: 1.25rem; margin: 0; display: flex; align-items: center; gap: 8px; }
  .badge { background: #388bfd26; color: var(--accent); padding: 4px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: bold; }
  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 16px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }
  .card-header { display: flex; justify-content: space-between; margin-bottom: 12px; }
  .resource { font-family: monospace; font-size: 0.95rem; font-weight: bold; color: #fff; word-break: break-all; }
  .score-badge { background: #d2992233; color: var(--warn); padding: 2px 8px; border-radius: 6px; font-size: 0.8rem; }
  .meta-row { font-size: 0.8rem; color: #8b949e; margin-bottom: 8px; }
  pre {
    background: #090d13; border: 1px solid #21262d; border-radius: 8px; padding: 10px; font-size: 0.8rem;
    overflow-x: auto; color: #e6edf3; font-family: "SF Mono", Consolas, monospace; line-height: 1.4;
  }
  .btn-group { display: flex; gap: 12px; margin-top: 16px; }
  button {
    flex: 1; padding: 12px; border-radius: 8px; border: none; font-weight: bold; font-size: 0.95rem; cursor: pointer;
    transition: opacity 0.2s;
  }
  button:active { opacity: 0.7; }
  .btn-approve { background: var(--green); color: #fff; }
  .btn-reject { background: var(--red); color: #fff; }
  .empty-state { text-align: center; padding: 40px 20px; color: #8b949e; }
</style>
</head>
<body>
<div class="header">
  <h1>🚦 SwarmGate Review</h1>
  <span class="badge">Live Tailnet</span>
</div>
<div id="cards-container">
  <!-- Dynamic cards inserted here -->
</div>
<script>
async function loadDecisions() {
  const res = await fetch('/api/decisions');
  const data = await res.json();
  const container = document.getElementById('cards-container');
  const keys = Object.keys(data);
  if (keys.length === 0) {
    container.innerHTML = '<div class="empty-state"><h3>🟢 All Clear</h3><p>No high-risk decisions pending operator attention.</p></div>';
    return;
  }
  container.innerHTML = keys.map(id => {
    const d = data[id];
    return `
      <div class="card" id="card-${id}">
        <div class="card-header">
          <div class="resource">${d.resource}</div>
          <span class="score-badge">Risk E=${d.escalation_score}</span>
        </div>
        <div class="meta-row">Agent: <b>${d.agent_id}</b> | Proof: ${d.card.proof_badge}</div>
        <pre>${d.card.compact_diff || '(No diff available)'}</pre>
        <div class="btn-group">
          <button class="btn-approve" onclick="resolve('${id}', true)">✓ Approve & Commit</button>
          <button class="btn-reject" onclick="resolve('${id}', false)">✗ Reject & Rollback</button>
        </div>
      </div>
    `;
  }).join('');
}
async function resolve(id, approved) {
  const el = document.getElementById('card-' + id);
  if (el) el.style.opacity = '0.4';
  await fetch(`/api/decisions/${id}/${approved ? 'approve' : 'reject'}`, { method: 'POST' });
  loadDecisions();
}
loadDecisions();
setInterval(loadDecisions, 3000);
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
        if parsed.path == "/" or parsed.path == "/index.html":
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
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        # /api/decisions/<id>/approve or reject
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decisions":
            dec_id = parts[2]
            action = parts[3].lower()
            if action in ["approve", "reject"]:
                ok = SwarmgateBridge.resolve_decision(dec_id, approved=(action == "approve"))
                self.send_response(200 if ok else 404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "SUCCESS" if ok else "NOT_FOUND"}).encode("utf-8"))
                return
        self.send_response(400)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Quiet logger


def run_server(host: Optional[str] = None, port: int = 8999):
    bind_host = host or get_tailscale_ip()
    server = HTTPServer((bind_host, port), SwarmgateHTTPHandler)
    print(f"🟢 SwarmGate Mobile Review Server listening on http://{bind_host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SwarmGate server...")
        server.server_close()