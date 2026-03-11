from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import get_history_dir, load_config
from .models import WorkflowConfig
from .runtime import load_history_entries


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Maker Checker Control Room</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #f3ede3;
      --panel: rgba(255, 250, 242, 0.88);
      --line: rgba(121, 98, 74, 0.22);
      --text: #181512;
      --muted: #6a5d50;
      --accent: #c45d29;
      --accent-2: #147364;
      --warn: #a53e2c;
      --idle: #7d7368;
      --shadow: 0 18px 42px rgba(59, 40, 20, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      font-family: "IBM Plex Sans", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(196, 93, 41, 0.18), transparent 26%),
        radial-gradient(circle at top right, rgba(20, 115, 100, 0.14), transparent 24%),
        linear-gradient(180deg, #f8f1e7 0%, var(--bg) 100%);
    }
    .shell {
      max-width: 1440px;
      margin: 0 auto;
      padding: 26px 18px 42px;
    }
    .hero {
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 18px;
      margin-bottom: 22px;
    }
    .hero h1 {
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.9rem);
      line-height: 0.93;
      letter-spacing: -0.05em;
    }
    .hero p {
      margin: 12px 0 0;
      max-width: 72ch;
      color: var(--muted);
    }
    .pill {
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 10px 14px;
      border-radius: 999px;
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      font-family: "IBM Plex Mono", monospace;
      font-size: 12px;
    }
    .layout {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      gap: 18px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      padding: 18px;
      backdrop-filter: blur(10px);
    }
    .panel h2 {
      margin: 0 0 12px;
      font-size: 0.92rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .sidebar {
      display: grid;
      gap: 18px;
      align-self: start;
      position: sticky;
      top: 18px;
    }
    .run-list {
      display: grid;
      gap: 10px;
    }
    .run-button {
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.75);
      border-radius: 16px;
      padding: 12px 14px;
      text-align: left;
      cursor: pointer;
      font: inherit;
      color: inherit;
      transition: transform 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
    }
    .run-button:hover {
      transform: translateY(-1px);
      border-color: var(--accent);
    }
    .run-button.active {
      border-color: var(--accent);
      box-shadow: inset 0 0 0 1px var(--accent);
    }
    .run-button strong {
      display: block;
      font-size: 0.98rem;
    }
    .run-meta {
      margin-top: 7px;
      display: flex;
      justify-content: space-between;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }
    .content {
      display: grid;
      gap: 18px;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
    }
    .metric {
      background: rgba(255,255,255,0.72);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
    }
    .metric label {
      display: block;
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .metric strong {
      display: block;
      font-size: 1.25rem;
      letter-spacing: -0.03em;
    }
    .progress-wrap {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }
    .bar {
      width: 100%;
      height: 12px;
      border-radius: 999px;
      background: rgba(104, 92, 79, 0.12);
      overflow: hidden;
    }
    .bar > span {
      display: block;
      height: 100%;
      background: linear-gradient(90deg, var(--accent), #f08a44);
      border-radius: 999px;
      transition: width 240ms ease;
    }
    .story-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .story {
      border-radius: 18px;
      padding: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
    }
    .story h3 {
      margin: 0 0 10px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }
    .story ul {
      margin: 0;
      padding-left: 18px;
    }
    .story li {
      margin: 0 0 8px;
    }
    .duo {
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(300px, 0.85fr);
      gap: 18px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    th, td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid rgba(121, 98, 74, 0.14);
      vertical-align: top;
    }
    th {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }
    .token {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 58px;
      padding: 6px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-family: "IBM Plex Mono", monospace;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: rgba(125, 115, 104, 0.12);
      color: var(--idle);
    }
    .token.run { background: rgba(20, 115, 100, 0.12); color: var(--accent-2); }
    .token.done { background: rgba(20, 115, 100, 0.18); color: var(--accent-2); }
    .token.fail { background: rgba(165, 62, 44, 0.14); color: var(--warn); }
    .token.todo { background: rgba(125, 115, 104, 0.12); color: var(--idle); }
    .stage-cards, .history-cards, .issues {
      display: grid;
      gap: 10px;
    }
    .stage-card, .history-card, .issue-card {
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      padding: 14px;
    }
    .stage-head, .history-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      margin-bottom: 10px;
    }
    .small {
      font-size: 12px;
      color: var(--muted);
    }
    .mono {
      font-family: "IBM Plex Mono", monospace;
      font-size: 12px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .log, .summary {
      min-height: 240px;
      border-radius: 18px;
      padding: 16px;
      background: #171614;
      color: #f8f3ea;
      white-space: pre-wrap;
      font-family: "IBM Plex Mono", monospace;
      font-size: 12px;
      line-height: 1.65;
      overflow: auto;
    }
    .empty {
      padding: 22px;
      border: 1px dashed var(--line);
      border-radius: 16px;
      color: var(--muted);
      text-align: center;
    }
    @media (max-width: 1120px) {
      .layout, .duo, .story-grid, .metric-grid { grid-template-columns: 1fr; }
      .sidebar { position: static; }
      .hero { flex-direction: column; align-items: start; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="hero">
      <div>
        <h1>Maker Checker<br>Control Room</h1>
        <p>Live local view of what happened, what is happening, what happens next, and where the run stands on verification and evaluation.</p>
      </div>
      <div class="pill">Auto refresh <span id="refreshTick">2s</span></div>
    </div>

    <div class="layout">
      <aside class="sidebar">
        <section class="panel">
          <h2>Runs</h2>
          <div id="runList" class="run-list"></div>
        </section>
        <section class="panel">
          <h2>Recent Learnings</h2>
          <div id="historyCards" class="history-cards"></div>
        </section>
      </aside>

      <main class="content">
        <section class="panel">
          <h2>Live Snapshot</h2>
          <div class="metric-grid">
            <div class="metric"><label>Run</label><strong id="runId">-</strong></div>
            <div class="metric"><label>State</label><strong id="runState">-</strong></div>
            <div class="metric"><label>Active</label><strong id="activeStage">-</strong></div>
            <div class="metric"><label>Next</label><strong id="nextStage">-</strong></div>
            <div class="metric"><label>Evaluation</label><strong id="evaluationState">-</strong></div>
          </div>
          <div class="progress-wrap">
            <div class="small" id="stageProgressText">0 / 0 stages complete</div>
            <div class="bar"><span id="stageProgressBar" style="width:0%"></span></div>
          </div>
        </section>

        <section class="panel">
          <h2>Run Story</h2>
          <div class="story-grid">
            <div class="story">
              <h3>What Happened</h3>
              <ul id="whatHappened"></ul>
            </div>
            <div class="story">
              <h3>What Is Happening</h3>
              <div id="whatIsHappening"></div>
            </div>
            <div class="story">
              <h3>What Happens Next</h3>
              <div id="whatHappensNext"></div>
            </div>
          </div>
        </section>

        <section class="duo">
          <section class="panel">
            <h2>Cycle Grid</h2>
            <div id="progressTable"></div>
          </section>
          <section class="panel">
            <h2>Evaluation Position</h2>
            <div class="metric-grid" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
              <div class="metric"><label>Verify</label><strong id="verifyState">-</strong></div>
              <div class="metric"><label>Evaluate</label><strong id="evaluateState">-</strong></div>
              <div class="metric"><label>Issues</label><strong id="issueCount">-</strong></div>
            </div>
            <div id="issueList" class="issues" style="margin-top: 12px;"></div>
          </section>
        </section>

        <section class="duo">
          <section class="panel">
            <h2>Stage Detail</h2>
            <div id="stageCards" class="stage-cards"></div>
          </section>
          <section class="panel">
            <h2>Runtime Log</h2>
            <div id="eventLog" class="log"></div>
          </section>
        </section>

        <section class="duo">
          <section class="panel">
            <h2>Summary</h2>
            <div id="runSummary" class="summary"></div>
          </section>
          <section class="panel">
            <h2>Paths</h2>
            <div class="stage-cards">
              <div class="stage-card">
                <div class="small">Task brief</div>
                <div id="taskBriefPath" class="mono"></div>
              </div>
              <div class="stage-card">
                <div class="small">Evaluation brief</div>
                <div id="evaluationBriefPath" class="mono"></div>
              </div>
              <div class="stage-card">
                <div class="small">Run summary file</div>
                <div id="runSummaryPath" class="mono"></div>
              </div>
              <div class="stage-card">
                <div class="small">History file</div>
                <div id="historyPath" class="mono"></div>
              </div>
            </div>
          </section>
        </section>
      </main>
    </div>
  </div>
  <script>
    const refreshMs = 2000;
    let selectedRun = null;

    function esc(value) {
      return String(value ?? "").replace(/[&<>"]/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[ch]));
    }

    function tokenClass(value) {
      return `token ${value || "todo"}`;
    }

    async function fetchJson(url) {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    }

    async function fetchText(url) {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.text();
    }

    function setText(id, value) {
      document.getElementById(id).textContent = value ?? "-";
    }

    function renderRuns(runs) {
      const root = document.getElementById("runList");
      if (!runs.length) {
        root.innerHTML = '<div class="empty">No runs yet.</div>';
        return;
      }
      const valid = runs.some(run => run.run_id === selectedRun);
      if (!valid) selectedRun = runs[0].run_id;
      root.innerHTML = runs.map(run => `
        <button class="run-button ${run.run_id === selectedRun ? "active" : ""}" data-run="${esc(run.run_id)}">
          <strong>${esc(run.run_id)}</strong>
          <div class="run-meta">
            <span>${esc(run.state || "unknown")}</span>
            <span>${esc(run.updated_at || run.started_at || "-")}</span>
          </div>
        </button>
      `).join("");
      root.querySelectorAll(".run-button").forEach(button => {
        button.onclick = () => {
          selectedRun = button.dataset.run;
          refresh();
        };
      });
    }

    function renderStoryList(id, items) {
      const root = document.getElementById(id);
      if (!items || !items.length) {
        root.innerHTML = '<li class="small">No events yet.</li>';
        return;
      }
      root.innerHTML = items.map(item => `<li>${esc(item)}</li>`).join("");
    }

    function renderProgress(status) {
      const root = document.getElementById("progressTable");
      if (!status.cycles || !status.cycles.length) {
        root.innerHTML = '<div class="empty">No cycle data yet.</div>';
        return;
      }
      const stageNames = ["plan", "critique", "revise", "execute", "verify", "evaluate"];
      const rows = status.cycles.map(cycle => `
        <tr>
          <td>${cycle.cycle}</td>
          ${stageNames.map(stage => `<td><span class="${tokenClass(cycle.stages[stage])}">${esc(cycle.stages[stage])}</span></td>`).join("")}
          <td>${cycle.issues_count}</td>
          <td>${cycle.elapsed_sec == null ? "-" : `${cycle.elapsed_sec.toFixed(1)}s`}</td>
        </tr>
      `).join("");
      root.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Cycle</th>
              ${stageNames.map(stage => `<th>${stage}</th>`).join("")}
              <th>Issues</th>
              <th>Duration</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }

    function renderIssues(status) {
      const root = document.getElementById("issueList");
      const issues = status.evaluation_state?.issues || [];
      if (!issues.length) {
        root.innerHTML = '<div class="empty">No unresolved issues in the current cycle.</div>';
        return;
      }
      root.innerHTML = issues.map(issue => `<div class="issue-card">${esc(issue)}</div>`).join("");
    }

    function renderStageCards(status) {
      const root = document.getElementById("stageCards");
      const cycle = status.active_cycle_snapshot || (status.cycles?.length ? status.cycles[status.cycles.length - 1] : null);
      if (!cycle || !cycle.stage_details || !cycle.stage_details.length) {
        root.innerHTML = '<div class="empty">No stage detail yet.</div>';
        return;
      }
      root.innerHTML = cycle.stage_details.map(stage => `
        <div class="stage-card">
          <div class="stage-head">
            <div>
              <strong>${esc(stage.stage)}</strong>
              <div class="small">agent: ${esc(stage.agent)}${stage.elapsed_sec == null ? "" : ` | ${stage.elapsed_sec.toFixed(1)}s`}</div>
            </div>
            <span class="${tokenClass(stage.status)}">${esc(stage.status)}</span>
          </div>
          <div class="small">command</div>
          <div class="mono">${esc(stage.command || "-")}</div>
          <div class="small" style="margin-top: 10px;">output excerpt</div>
          <div class="mono">${esc(stage.output_excerpt || "No output yet.")}</div>
        </div>
      `).join("");
    }

    function renderHistory(entries) {
      const root = document.getElementById("historyCards");
      if (!entries.length) {
        root.innerHTML = '<div class="empty">No historical learnings yet.</div>';
        return;
      }
      root.innerHTML = entries.map(entry => `
        <div class="history-card">
          <div class="history-head">
            <strong>${esc(entry.run_id)}</strong>
            <span class="small">${esc(entry.outcome)}</span>
          </div>
          <div class="small">Trend: ${esc(entry.issue_trend)}</div>
          <div style="margin-top:8px;">${esc((entry.next_run_notes || []).join(" | ") || "No carry-forward note.")}</div>
        </div>
      `).join("");
    }

    function renderStatus(status, summary) {
      setText("runId", status.run_id || "-");
      setText("runState", status.state || "-");
      setText("activeStage", status.active_stage ? `cycle ${status.active_cycle} / ${status.active_stage}` : "idle");
      setText("nextStage", status.next_stage || "none");
      setText("evaluationState", status.evaluation_state?.evaluate_pass === true ? "pass" : status.evaluation_state?.evaluate_pass === false ? "fail" : "pending");
      setText("verifyState", status.evaluation_state?.verify_pass === true ? "pass" : status.evaluation_state?.verify_pass === false ? "fail" : "pending");
      setText("evaluateState", status.evaluation_state?.evaluate_pass === true ? "pass" : status.evaluation_state?.evaluate_pass === false ? "fail" : "pending");
      setText("issueCount", status.evaluation_state?.issues_count ?? 0);
      setText("taskBriefPath", status.task_brief_path || "-");
      setText("evaluationBriefPath", status.evaluation_brief_path || "-");
      setText("runSummaryPath", status.run_summary_file || "-");
      setText("historyPath", status.history_file || "-");

      const completed = status.stage_position?.completed || 0;
      const total = status.stage_position?.total || 0;
      const percent = total ? Math.round((completed / total) * 100) : 0;
      setText("stageProgressText", `${completed} / ${total} stages complete`);
      document.getElementById("stageProgressBar").style.width = `${percent}%`;

      renderStoryList("whatHappened", status.what_happened || []);
      document.getElementById("whatIsHappening").textContent = status.what_is_happening || "-";
      document.getElementById("whatHappensNext").textContent = status.what_happens_next || "-";
      document.getElementById("eventLog").textContent = (status.recent_events || []).join("\\n") || "No events yet.";
      document.getElementById("runSummary").textContent = summary || "No summary yet.";
      renderProgress(status);
      renderIssues(status);
      renderStageCards(status);
    }

    async function refresh() {
      try {
        const runs = await fetchJson("/api/runs");
        renderRuns(runs);
        const runQuery = selectedRun ? `?run=${encodeURIComponent(selectedRun)}` : "";
        const [status, summary, history] = await Promise.all([
          fetchJson(`/api/status${runQuery}`),
          fetchText(`/api/summary${runQuery}`),
          fetchJson("/api/history"),
        ]);
        renderStatus(status, summary);
        renderHistory(history);
      } catch (err) {
        document.getElementById("eventLog").textContent = `Dashboard error: ${err.message}`;
      }
    }

    document.getElementById("refreshTick").textContent = `${refreshMs / 1000}s`;
    refresh();
    setInterval(refresh, refreshMs);
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the local maker-checker dashboard.")
    parser.add_argument("--config", default="config.toml", help="Path to workflow config TOML.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    return parser.parse_args()


def list_runs(config: WorkflowConfig) -> list[dict[str, str | None]]:
    runs: list[dict[str, str | None]] = []
    if not config.artifacts_dir.exists():
        return runs

    for path in sorted(config.artifacts_dir.iterdir(), reverse=True):
        if not path.is_dir():
            continue
        status_path = path / "status.json"
        summary_path = path / "summary.json"
        status = {}
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding="utf-8"))
        elif summary_path.exists():
            status = json.loads(summary_path.read_text(encoding="utf-8"))
        runs.append(
            {
                "run_id": path.name,
                "state": status.get("state") or ("completed" if status.get("completed") else "incomplete"),
                "started_at": status.get("started_at"),
                "updated_at": status.get("updated_at") or status.get("ended_at"),
            }
        )
    return runs


def load_status(config: WorkflowConfig, run_id: str | None) -> dict:
    if run_id:
        path = config.artifacts_dir / run_id / "status.json"
    else:
        path = config.artifacts_dir / "latest_status.json"
    if not path.exists():
        return {
            "run_id": None,
            "state": "idle",
            "active_cycle": None,
            "active_stage": None,
            "next_stage": None,
            "updated_at": None,
            "stage_position": {"completed": 0, "total": 0},
            "evaluation_state": {"verify_pass": None, "evaluate_pass": None, "issues_count": 0, "issues": []},
            "what_happened": [],
            "what_is_happening": "No run activity yet.",
            "what_happens_next": "Start a run to populate the dashboard.",
            "cycles": [],
            "recent_events": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def load_summary_text(config: WorkflowConfig, run_id: str | None) -> str:
    if run_id:
        path = config.artifacts_dir / run_id / "run_summary.md"
    else:
        latest = load_status(config, None).get("run_id")
        path = (
            config.artifacts_dir / latest / "run_summary.md"
            if latest
            else config.artifacts_dir / "latest_summary.md"
        )
    if not path.exists():
        return "No summary yet."
    return path.read_text(encoding="utf-8")


def load_history(config: WorkflowConfig, limit: int = 8) -> list[dict]:
    return load_history_entries(get_history_dir(config))[-limit:][::-1]


def make_handler(config: WorkflowConfig):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            run_id = params.get("run", [None])[0]

            if parsed.path == "/":
                self._send(HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/runs":
                self._send(json.dumps(list_runs(config)).encode("utf-8"), "application/json")
                return
            if parsed.path == "/api/status":
                self._send(json.dumps(load_status(config, run_id)).encode("utf-8"), "application/json")
                return
            if parsed.path == "/api/history":
                self._send(json.dumps(load_history(config)).encode("utf-8"), "application/json")
                return
            if parsed.path == "/api/summary":
                self._send(load_summary_text(config, run_id).encode("utf-8"), "text/plain; charset=utf-8")
                return

            self._send(b"Not found", "text/plain; charset=utf-8", status=404)

    return Handler


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config).expanduser().resolve())
    server = ThreadingHTTPServer((args.host, args.port), make_handler(config))
    print(f"Dashboard running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
