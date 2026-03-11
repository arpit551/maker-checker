const REFRESH_MS = 2000;
const STAGE_ORDER = ["plan", "critique", "revise", "execute", "verify", "evaluate"];
const RUN_TABS = [
  ["prompt", "Prompt"],
  ["logs", "Logs"],
  ["output", "Output"],
  ["summary", "Summary"],
  ["live", "Live"],
];
const LOG_STREAMS = ["combined", "assistant_output", "stdout", "stderr"];

const uiState = {
  refreshTick: 0,
  runs: {},
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
}

function shortText(value, fallback = "-") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function formatSeconds(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(1)}s`;
}

function formatTimestamp(value) {
  const text = shortText(value, "");
  if (!text) return "-";
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return text;
  return parsed.toLocaleString();
}

function passLabel(value) {
  if (value === true) return "pass";
  if (value === false) return "fail";
  return "pending";
}

function badgeClass(kind, value) {
  const normalized = String(value || "pending").toLowerCase();
  return `badge ${kind}-${normalized}`;
}

function stageStateClass(value) {
  const normalized = String(value || "pending").toLowerCase();
  if (normalized === "running" || normalized === "run") return "stage-running";
  if (normalized === "completed" || normalized === "done") return "stage-completed";
  if (normalized === "failed" || normalized === "fail") return "stage-failed";
  return "stage-pending";
}

function currentCycle(status) {
  return status.active_cycle_snapshot || (status.cycles?.length ? status.cycles[status.cycles.length - 1] : null);
}

function currentStages(status) {
  return currentCycle(status)?.stage_details || [];
}

function chooseDefaultStage(status) {
  const stages = currentStages(status);
  if (!stages.length) return null;
  if (status.active_stage) return status.active_stage;
  const latestStarted = [...stages].reverse().find((stage) => !["pending", "todo", ""].includes(String(stage.status || "").toLowerCase()));
  return latestStarted?.stage || stages[0].stage;
}

function defaultTab(status) {
  return status.state === "running" ? "live" : "output";
}

function totalRuntime(status) {
  if (status.runtime_totals?.seconds_running != null) return formatSeconds(status.runtime_totals.seconds_running);
  const total = (status.cycles || []).reduce((sum, cycle) => sum + (Number(cycle.elapsed_sec) || 0), 0);
  return total ? formatSeconds(total) : "-";
}

function issueCount(status) {
  return status.evaluation_state?.issues_count ?? currentCycle(status)?.issues_count ?? 0;
}

function isRunLive(status) {
  return status.state === "running" && Boolean(status.active_stage) && Boolean(status.active_cycle);
}

function ensureRunState(runId, status = null) {
  if (!uiState.runs[runId]) {
    uiState.runs[runId] = {
      open: false,
      selectedStage: null,
      selectedTab: null,
      selectedLogStream: "combined",
      lastHtml: "",
    };
  }
  const state = uiState.runs[runId];
  if (status) {
    const stageNames = currentStages(status).map((stage) => stage.stage);
    if (!state.selectedStage || (stageNames.length && !stageNames.includes(state.selectedStage))) {
      state.selectedStage = chooseDefaultStage(status);
    }
    if (!state.selectedTab) {
      state.selectedTab = defaultTab(status);
    }
    if (!LOG_STREAMS.includes(state.selectedLogStream)) {
      state.selectedLogStream = "combined";
    }
  }
  return state;
}

function syncRunState(runs) {
  const runIds = new Set(runs.map((run) => run.run_id));
  for (const runId of Object.keys(uiState.runs)) {
    if (!runIds.has(runId)) delete uiState.runs[runId];
  }
  if (!runs.length) return;
  const hasOpenRun = runs.some((run) => uiState.runs[run.run_id]?.open);
  if (!hasOpenRun) {
    const preferred = runs.find((run) => run.state === "running")?.run_id || runs[0].run_id;
    ensureRunState(preferred).open = true;
  }
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

function getRunRoot(runId) {
  return [...document.querySelectorAll(".run-accordion")].find((node) => node.dataset.runId === runId) || null;
}

function getRunBody(runId) {
  return getRunRoot(runId)?.querySelector(".run-detail") || null;
}

function renderHistory(entries) {
  const root = document.getElementById("historyCards");
  if (!entries.length) {
    root.innerHTML = '<div class="empty">No historical learnings yet.</div>';
    return;
  }

  root.innerHTML = entries.map((entry) => `
    <article class="history-card">
      <div class="history-top">
        <strong>${esc(entry.run_id)}</strong>
        <span class="${badgeClass("state", entry.outcome || "pending")}">${esc(entry.outcome || "unknown")}</span>
      </div>
      <div class="small">Trend: ${esc(entry.issue_trend || "unknown")}</div>
      <div>${esc((entry.next_run_notes || []).join(" | ") || "No carry-forward note.")}</div>
    </article>
  `).join("");
}

function renderRunSummary(run) {
  const activeLabel = run.state === "running" && run.active_stage ? `cycle ${run.active_cycle} / ${run.active_stage}` : "idle";
  const runtime = formatSeconds(run.seconds_running);
  const cachedHtml = uiState.runs[run.run_id]?.lastHtml || '<div class="loading">Loading run detail...</div>';
  return `
    <details class="run-accordion" data-run-id="${esc(run.run_id)}" ${uiState.runs[run.run_id]?.open ? "open" : ""}>
      <summary class="run-summary">
        <div class="run-summary-grid">
          <div class="run-title">
            <div class="run-title-line">
              <strong class="run-name">${esc(run.run_id)}</strong>
              <span class="${badgeClass("state", run.state || "unknown")}">${esc(run.state || "unknown")}</span>
            </div>
            <div class="run-subtitle">Updated ${esc(formatTimestamp(run.updated_at || run.started_at))}</div>
            <div class="run-badge-row">
              <span class="badge">${esc(activeLabel)}</span>
              <span class="badge">${esc(`issues ${run.issues_count ?? 0}`)}</span>
              <span class="badge">${esc(runtime)}</span>
            </div>
          </div>
          <div class="run-meta-row">
            <span class="badge">${esc(`started ${formatTimestamp(run.started_at)}`)}</span>
            <span class="badge">${esc(shortText(run.last_event, "no recent event"))}</span>
            <span class="badge ${run.last_error ? "fail" : "pending"}">${esc(run.last_error ? "has error" : "no error")}</span>
          </div>
        </div>
      </summary>
      <div class="run-detail">
        ${cachedHtml}
      </div>
    </details>
  `;
}

function renderRuns(runs) {
  syncRunState(runs);
  const root = document.getElementById("runAccordions");
  document.getElementById("runsMeta").textContent = `${runs.length} run${runs.length === 1 ? "" : "s"}`;
  if (!runs.length) {
    root.innerHTML = '<div class="empty">No runs yet.</div>';
    return;
  }

  root.innerHTML = runs.map(renderRunSummary).join("");
  root.querySelectorAll(".run-accordion").forEach((node) => {
    node.addEventListener("toggle", () => {
      ensureRunState(node.dataset.runId).open = node.open;
      if (node.open) {
        loadAndRenderRun(node.dataset.runId, window.__lastState || {}, uiState.refreshTick);
      }
    });
  });
}

async function loadRunDetail(runId, state) {
  if (state.current_run?.run_id === runId) return state.current_run;
  return await fetchJson(`/api/v1/runs/${encodeURIComponent(runId)}`);
}

async function loadStageDetail(runId, cycle, stage) {
  return await fetchJson(`/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stage)}?cycle=${encodeURIComponent(cycle)}`);
}

async function loadStageLogs(runId, cycle, stage, limit = null) {
  const suffix = limit ? `&limit=${encodeURIComponent(limit)}` : "";
  return await fetchJson(`/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stage)}/logs?cycle=${encodeURIComponent(cycle)}${suffix}`);
}

function renderMetricCards(status) {
  const cycle = currentCycle(status);
  const metrics = [
    ["State", status.state || "-"],
    ["Current Cycle", cycle?.cycle ?? "-"],
    ["Active Stage", isRunLive(status) ? status.active_stage : "idle"],
    ["Next Stage", status.next_stage || "none"],
    ["Issues", issueCount(status)],
    ["Runtime", totalRuntime(status)],
    ["Started", formatTimestamp(status.started_at)],
    ["Updated", formatTimestamp(status.updated_at || status.ended_at || status.started_at)],
  ];

  return metrics.map(([label, value]) => `
    <div class="metric-card">
      <span class="metric-label">${esc(label)}</span>
      <span class="metric-value ${String(value).length > 36 ? "tight" : ""}">${esc(value)}</span>
    </div>
  `).join("");
}

function renderStageStrip(status, runState) {
  const stagesByName = Object.fromEntries(currentStages(status).map((stage) => [stage.stage, stage]));
  return STAGE_ORDER.map((stageName) => {
    const stage = stagesByName[stageName] || { stage: stageName, status: "pending" };
    const selected = runState.selectedStage === stageName;
    const klass = `${stageStateClass(stage.status)} ${selected ? "active" : ""}`;
    return `
      <button class="stage-pill ${klass}" data-stage-button="${esc(stageName)}" type="button">
        <span class="stage-pill-label">${esc(stageName)}</span>
        <span class="stage-pill-state">${esc(stage.status || "pending")}</span>
      </button>
    `;
  }).join("");
}

function renderTabRow(runState) {
  return RUN_TABS.map(([tabId, label]) => `
    <button class="tab-button ${runState.selectedTab === tabId ? "active" : ""}" data-tab-button="${esc(tabId)}" type="button">${esc(label)}</button>
  `).join("");
}

function stageMeta(detail) {
  if (!detail) return "";
  const bits = [`cycle ${detail.cycle}`, detail.stage, detail.agent || "-"];
  const sessionId = detail.reported_session_id || detail.session_id;
  if (sessionId) bits.push(`session ${sessionId}`);
  if (detail.elapsed_sec != null) bits.push(formatSeconds(detail.elapsed_sec));
  return bits.join(" | ");
}

function renderTextTab(detail, text, emptyText) {
  if (!detail) {
    return `<div class="empty">${esc(emptyText)}</div>`;
  }
  return `
    <div class="tab-meta">${esc(stageMeta(detail))}</div>
    <pre class="console stage-console">${esc(text || emptyText)}</pre>
  `;
}

function resolveSelectedStream(runState, logs) {
  const available = LOG_STREAMS.filter((name) => logs?.streams?.[name]?.exists || logs?.streams?.[name]?.text);
  if (!available.length) return null;
  if (!available.includes(runState.selectedLogStream)) {
    runState.selectedLogStream = available[0];
  }
  return runState.selectedLogStream;
}

function renderLogsTab(runState, detail, logs) {
  if (!detail || !logs) {
    return '<div class="empty">No logs available for this stage yet.</div>';
  }

  const selectedStream = resolveSelectedStream(runState, logs);
  if (!selectedStream) {
    return `<div class="tab-meta">${esc(stageMeta(detail))}</div><div class="empty">No log streams captured yet.</div>`;
  }

  const stream = logs.streams[selectedStream];
  return `
    <div class="tab-meta">${esc(stageMeta(detail))} | ${esc(selectedStream)} | ${esc(stream.path || "-")}</div>
    <div class="stream-row">
      ${LOG_STREAMS.filter((name) => logs.streams?.[name]?.exists || logs.streams?.[name]?.text).map((name) => `
        <button class="stream-button ${selectedStream === name ? "active" : ""}" data-log-stream="${esc(name)}" type="button">${esc(name)}</button>
      `).join("")}
    </div>
    <pre class="console stage-console">${esc(stream.text || "No raw log output yet.")}</pre>
  `;
}

function renderSummaryTab(status) {
  const issues = status.evaluation_state?.issues || currentCycle(status)?.issues || [];
  const failure = status.failure?.error || "none";
  return `
    <div class="summary-grid">
      <section class="story">
        <h3>Run Summary</h3>
        <pre class="console summary-console">${esc(status.summary_markdown || "No summary yet.")}</pre>
      </section>
      <div class="summary-aside">
        <section class="story">
          <h3>Evaluation</h3>
          <div class="metric-grid">
            <div class="metric-card">
              <span class="metric-label">Verify</span>
              <span class="metric-value">${esc(passLabel(status.evaluation_state?.verify_pass))}</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Evaluate</span>
              <span class="metric-value">${esc(passLabel(status.evaluation_state?.evaluate_pass))}</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Issues</span>
              <span class="metric-value">${esc(issueCount(status))}</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Failure</span>
              <span class="metric-value tight">${esc(failure)}</span>
            </div>
          </div>
        </section>
        <section class="story">
          <h3>Current Issues</h3>
          <div class="issue-grid">
            ${issues.length ? issues.map((issue) => `<div class="issue-card">${esc(issue)}</div>`).join("") : '<div class="empty">No unresolved issues in the latest cycle.</div>'}
          </div>
        </section>
      </div>
    </div>
  `;
}

function renderLiveTab(status, liveDetail, liveLogs) {
  const liveText = liveLogs?.streams?.combined?.text || liveLogs?.streams?.assistant_output?.text || "No live log output yet.";
  const sessionId = liveDetail?.reported_session_id || liveDetail?.session_id || "-";
  const live = isRunLive(status);
  return `
    <div class="live-grid">
      <section class="story">
        <h3>What Is Happening</h3>
        <p class="story-copy">${esc(status.what_is_happening || "No stage is currently running.")}</p>
      </section>
      <section class="story">
        <h3>What Happens Next</h3>
        <p class="story-copy">${esc(status.what_happens_next || "No next step reported yet.")}</p>
      </section>
      <section class="story">
        <h3>Live Context</h3>
        <div class="run-badge-row">
          <span class="badge ${live ? "stage-running" : "pending"}">${esc(live ? `active ${status.active_stage}` : "idle")}</span>
          <span class="badge">${esc(live ? `cycle ${status.active_cycle}` : "no active cycle")}</span>
          <span class="badge">${esc(`session ${sessionId}`)}</span>
        </div>
      </section>
      <section class="story">
        <h3>Recent Events</h3>
        <pre class="console">${esc((status.recent_events || []).join("\n") || "No recent events yet.")}</pre>
      </section>
      <section class="story">
        <h3>Live Logs</h3>
        <div class="tab-meta">${esc(live ? stageMeta(liveDetail) : "No stage is currently running")}</div>
        <pre class="console stage-console">${esc(liveText)}</pre>
      </section>
    </div>
  `;
}

function renderTabContent(status, runState, resources) {
  if (runState.selectedTab === "summary") {
    return renderSummaryTab(status);
  }
  if (runState.selectedTab === "live") {
    return renderLiveTab(status, resources.liveDetail, resources.liveLogs);
  }
  if (runState.selectedTab === "prompt") {
    return renderTextTab(resources.stageDetail, resources.stageDetail?.content?.prompt, "No prompt recorded for this stage.");
  }
  if (runState.selectedTab === "logs") {
    return renderLogsTab(runState, resources.stageDetail, resources.stageLogs);
  }
  return renderTextTab(
    resources.stageDetail,
    resources.stageDetail?.content?.assistant_output || resources.stageDetail?.content?.primary_output,
    "No output captured for this stage yet.",
  );
}

async function gatherRunResources(status, runState) {
  const cycle = currentCycle(status);
  const resources = {
    stageDetail: null,
    stageLogs: null,
    liveDetail: null,
    liveLogs: null,
  };

  const selectedStage = runState.selectedStage;
  if (cycle?.cycle && selectedStage && ["output", "prompt", "logs"].includes(runState.selectedTab)) {
    resources.stageDetail = await loadStageDetail(status.run_id, cycle.cycle, selectedStage);
    if (runState.selectedTab === "logs") {
      resources.stageLogs = await loadStageLogs(status.run_id, cycle.cycle, selectedStage);
    }
  }

  if (runState.selectedTab === "live" && isRunLive(status)) {
    const [liveDetail, liveLogs] = await Promise.all([
      loadStageDetail(status.run_id, status.active_cycle, status.active_stage),
      loadStageLogs(status.run_id, status.active_cycle, status.active_stage, 12000),
    ]);
    resources.liveDetail = liveDetail;
    resources.liveLogs = liveLogs;
  }

  return resources;
}

async function buildRunDetail(status) {
  const runState = ensureRunState(status.run_id, status);
  const resources = await gatherRunResources(status, runState);
  return `
    <div>
      <div class="section-label">Run Snapshot</div>
      <div class="metric-grid">${renderMetricCards(status)}</div>
    </div>
    <div>
      <div class="section-label">Stage</div>
      <div class="stage-strip">${renderStageStrip(status, runState)}</div>
    </div>
    <div>
      <div class="section-label">View</div>
      <div class="tab-row">${renderTabRow(runState)}</div>
    </div>
    <div class="run-panel-surface">
      ${renderTabContent(status, runState, resources)}
    </div>
  `;
}

function bindRunControls(runId) {
  const body = getRunBody(runId);
  if (!body) return;

  body.querySelectorAll("[data-stage-button]").forEach((button) => {
    button.addEventListener("click", async () => {
      const runState = ensureRunState(runId);
      runState.selectedStage = button.dataset.stageButton;
      runState.selectedLogStream = "combined";
      if (["summary", "live"].includes(runState.selectedTab)) {
        runState.selectedTab = "output";
      }
      await loadAndRenderRun(runId, window.__lastState || {}, uiState.refreshTick);
    });
  });

  body.querySelectorAll("[data-tab-button]").forEach((button) => {
    button.addEventListener("click", async () => {
      const runState = ensureRunState(runId);
      runState.selectedTab = button.dataset.tabButton;
      if (runState.selectedTab === "logs") {
        runState.selectedLogStream = "combined";
      }
      await loadAndRenderRun(runId, window.__lastState || {}, uiState.refreshTick);
    });
  });

  body.querySelectorAll("[data-log-stream]").forEach((button) => {
    button.addEventListener("click", async () => {
      ensureRunState(runId).selectedLogStream = button.dataset.logStream;
      await loadAndRenderRun(runId, window.__lastState || {}, uiState.refreshTick);
    });
  });
}

async function loadAndRenderRun(runId, state, refreshId) {
  const root = getRunRoot(runId);
  const body = getRunBody(runId);
  if (!root || !body || !root.open) return;

  if (!body.innerHTML.trim()) {
    body.innerHTML = '<div class="loading">Loading run detail...</div>';
  }
  try {
    const status = await loadRunDetail(runId, state);
    const html = await buildRunDetail(status);
    if (refreshId !== uiState.refreshTick || !root.open) return;
    ensureRunState(runId).lastHtml = html;
    body.innerHTML = html;
    bindRunControls(runId);
  } catch (err) {
    if (refreshId !== uiState.refreshTick) return;
    const errorHtml = `<div class="empty">Run detail error: ${esc(err.message)}</div>`;
    ensureRunState(runId).lastHtml = errorHtml;
    body.innerHTML = errorHtml;
  }
}

async function renderOpenRuns(state, refreshId) {
  const openRunIds = Object.entries(uiState.runs)
    .filter(([, value]) => value.open)
    .map(([runId]) => runId);
  await Promise.all(openRunIds.map((runId) => loadAndRenderRun(runId, state, refreshId)));
}

async function refresh() {
  const refreshId = ++uiState.refreshTick;
  try {
    const state = await fetchJson("/api/v1/state");
    window.__lastState = state;
    renderRuns(state.runs || []);
    renderHistory(state.history || []);
    await renderOpenRuns(state, refreshId);
  } catch (err) {
    document.getElementById("runAccordions").innerHTML = `<div class="empty">Dashboard error: ${esc(err.message)}</div>`;
  }
}

document.getElementById("refreshTick").textContent = `${REFRESH_MS / 1000}s`;
refresh();
setInterval(refresh, REFRESH_MS);
