import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_NERAIUM_API_BASE || "/api";
const SIGNAL_NAMES = [
  "spindle_vibration",
  "spindle_motor_current",
  "coolant_flow_rate",
  "axis_servo_load",
  "cutting_zone_temperature",
];
const SIGNAL_LABELS = {
  sensor_0: "Spindle Vibration",
  sensor_1: "Spindle Motor Current",
  sensor_2: "Coolant Flow Rate",
  sensor_3: "Axis Servo Load",
  sensor_4: "Cutting Zone Temperature",
};
const GRAPH_NODES = [
  { id: "sensor_0", x: 50, y: 40 },
  { id: "sensor_1", x: 250, y: 40 },
  { id: "sensor_2", x: 50, y: 170 },
  { id: "sensor_3", x: 250, y: 170 },
  { id: "sensor_4", x: 150, y: 105 },
];

function createRng(seed = 42) {
  let state = seed >>> 0;
  return () => {
    state = (1664525 * state + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function normal(rng, mean = 0, std = 1) {
  const u1 = Math.max(rng(), Number.EPSILON);
  const u2 = rng();
  const z0 = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  return mean + std * z0;
}

function demoPacket(cycle, rng) {
  const signals = {
    spindle_vibration: normal(rng, 0, 1),
    spindle_motor_current: normal(rng, 0, 1),
    coolant_flow_rate: normal(rng, 0, 1),
    axis_servo_load: normal(rng, 0, 1),
    cutting_zone_temperature: normal(rng, 0, 1),
  };

  if (cycle >= 70) {
    const progress = (cycle - 70) / 120;
    const shared = normal(rng, 0, 1);
    const coupling = 0.35 + 1.25 * progress;
    const drift = 0.02 * (cycle - 70);

    signals.spindle_vibration = coupling * shared + drift;
    signals.spindle_motor_current = coupling * shared + normal(rng, 0, 0.04) + drift;
    signals.coolant_flow_rate = normal(rng, 0, 1);
    signals.axis_servo_load = normal(rng, 0, 1);
    signals.cutting_zone_temperature = normal(rng, 0, 1);
  }

  return SIGNAL_NAMES.reduce((ordered, name) => {
    ordered[name] = signals[name];
    return ordered;
  }, {});
}

async function postJson(path, payload, apiBase) {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }

  return response.json();
}

async function getJson(path, apiBase) {
  const response = await fetch(`${apiBase}${path}`);

  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }

  return response.json();
}

function App() {
  const [systemOutput, setSystemOutput] = useState({
    operator: { status: "INITIALIZING" },
    engineer: { status: "INITIALIZING" },
  });
  const [cycle, setCycle] = useState(0);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [history, setHistory] = useState([]);
  const [activeTab, setActiveTab] = useState("operator");
  const [apiBase, setApiBase] = useState(API_BASE);
  const [sourceMode, setSourceMode] = useState("demo");
  const [csvRows, setCsvRows] = useState([]);
  const [csvName, setCsvName] = useState("");
  const [csvError, setCsvError] = useState("");
  const [backendConnected, setBackendConnected] = useState(false);
  const [lastUpdateAt, setLastUpdateAt] = useState(null);
  const [demoSpeedMs, setDemoSpeedMs] = useState(450);
  const timerRef = useRef(null);
  const rngRef = useRef(createRng(42));
  const cycleRef = useRef(0);

  const operator = systemOutput.operator || { status: "INITIALIZING" };
  const engineer = systemOutput.engineer || { status: "INITIALIZING" };
  const urgency = operator.trajectory?.urgency || "low";
  const direction = operator.trajectory?.direction || "not established";
  const status = operator.status || "INITIALIZING";
  const metrics = engineer.structural_metrics || {};
  const evidence = engineer.evidence || {};
  const relationships = engineer.contributors?.top_relationships || [];

  const statusTone = useMemo(() => {
    if (status === "CONFIRMED_CHANGE" || status === "CONFIRMED_CHANGE_HELD") {
      return urgency === "high" ? "critical" : "active";
    }
    if (status === "TRANSIENT") return "quiet";
    return "initializing";
  }, [status, urgency]);

  async function resetDemo() {
    stopDemo();
    setError("");
    cycleRef.current = 0;
    rngRef.current = createRng(42);
    setCycle(0);
    setHistory([]);
    const output = await postJson("/reset", {}, apiBase);
    setBackendConnected(true);
    setLastUpdateAt(null);
    setSystemOutput({
      operator: { status: output.status === "reset" ? "INITIALIZING" : output.status },
      engineer: { status: output.status === "reset" ? "INITIALIZING" : output.status },
    });
  }

  async function sendCycle() {
    const currentCycle = cycleRef.current;
    const signals =
      sourceMode === "csv" && csvRows.length > 0
        ? csvRows[currentCycle]
        : demoPacket(currentCycle, rngRef.current);

    if (!signals) {
      stopDemo();
      return;
    }

    const payload = {
      asset_id: "CNC-01",
      signals,
    };

    const output = await postJson("/update", payload, apiBase);
    setBackendConnected(true);
    setLastUpdateAt(new Date().toLocaleTimeString());
    setSystemOutput(output);
    setHistory((items) => [...items, { cycle: currentCycle, output }].slice(-50));
    setCycle(currentCycle);
    cycleRef.current = currentCycle + 1;
  }

  function startTimer(intervalMs) {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
    }

    timerRef.current = window.setInterval(() => {
      sendCycle().catch((err) => {
        setError(err.message);
        setBackendConnected(false);
        stopDemo();
      });
    }, intervalMs);
  }

  function startDemo() {
    if (timerRef.current) return;
    setError("");
    setIsRunning(true);
    startTimer(demoSpeedMs);
  }

  function stopDemo() {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRunning(false);
  }

  function updateDemoSpeed(event) {
    const nextSpeed = Number(event.target.value);
    setDemoSpeedMs(nextSpeed);

    if (timerRef.current) {
      startTimer(nextSpeed);
    }
  }

  useEffect(() => {
    return () => stopDemo();
  }, []);

  useEffect(() => {
    let active = true;
    getJson("/health", apiBase)
      .then(() => {
        if (active) {
          setBackendConnected(true);
        }
      })
      .catch(() => {
        if (active) {
          setBackendConnected(false);
        }
      });

    return () => {
      active = false;
    };
  }, [apiBase]);

  return (
    <main className="console-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Live structural visibility for industrial systems</p>
          <h1>Neraium Operator Console</h1>
        </div>
        <div className="cycle-readout">
          <span>Cycle</span>
          <strong>{cycle}</strong>
        </div>
      </header>

      <nav className="tabbar" aria-label="Console sections">
        <button
          type="button"
          className={activeTab === "operator" ? "active" : ""}
          onClick={() => setActiveTab("operator")}
        >
          Operator
        </button>
        <button
          type="button"
          className={activeTab === "relationships" ? "active" : ""}
          onClick={() => setActiveTab("relationships")}
        >
          Relationships
        </button>
        <button
          type="button"
          className={activeTab === "evidence" ? "active" : ""}
          onClick={() => setActiveTab("evidence")}
        >
          Evidence
        </button>
        <button
          type="button"
          className={activeTab === "controls" ? "active" : ""}
          onClick={() => setActiveTab("controls")}
        >
          Demo
        </button>
        <button
          type="button"
          className={activeTab === "settings" ? "active" : ""}
          onClick={() => setActiveTab("settings")}
        >
          Settings
        </button>
      </nav>

      {activeTab === "operator" && (
        <>
      <section className={`asset-panel ${statusTone}`}>
        <div className="asset-heading">
          <div>
            <p className="label">Asset</p>
            <h2>CNC-01</h2>
          </div>
          <StatusBadge status={status} urgency={urgency} />
        </div>

        <OperatorAlert operator={operator} status={status} direction={direction} urgency={urgency} />
      </section>

      <StructuralStateStrip metrics={metrics} evidence={evidence} />

      <section className="story-layout operator-only">
        <article className="operator-story">
          <p className="label">Operator Story</p>
          <h3>{operatorSummary(status, operator)}</h3>
          <p className="story-copy">
            {operatorMeaning(status, operator)}
          </p>

          <div className="story-block">
            <span>Where to look</span>
            <ul>
              {(operator.where_to_look?.subsystems || ["Awaiting confirmed evidence"]).map(
                (item) => (
                  <li key={item}>{item}</li>
                ),
              )}
            </ul>
          </div>

          <div className="story-block">
            <span>Recommended checks</span>
            <ol>
              {(operator.recommended_checks || ["Continue monitoring until a confirmed structural change appears."]).map(
                (item) => (
                  <li key={item}>{item}</li>
                ),
              )}
            </ol>
          </div>

          <div className="story-block">
            <span>Decision basis</span>
            <ul>
              {(operator.decision_basis || ["No confirmed structural change."]).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>

          <div className="story-block">
            <span>Watch next</span>
            <p>{watchNextCopy(operator.watch_next)}</p>
          </div>

          <div className="story-block">
            <span>Why it matters</span>
            <p>{operator.why_it_matters?.meaning || "No structural change is confirmed yet."}</p>
          </div>

          <div className="story-block muted">
            <span>If ignored</span>
            <p>{operator.if_ignored?.expected_behavior || "No confirmed behavior to project."}</p>
          </div>

          <div className="story-block muted">
            <span>What this does not claim</span>
            <p>
              {operator.plain_english?.what_we_are_not_claiming ||
                "This view does not claim a failure mode, failure time, or exact physical cause."}
            </p>
          </div>
        </article>
      </section>
        </>
      )}

      {activeTab === "relationships" && (
        <section className="insight-layout single-tab">
          <LiveRelationshipGraph
            operator={operator}
            relationships={relationships}
            status={status}
            metrics={metrics}
          />
          <EvidenceTimeline history={history} />
        </section>
      )}

      {activeTab === "evidence" && (
      <section className="engineer-section">
        <button
          type="button"
          className="drawer-toggle"
          onClick={() => setDrawerOpen((open) => !open)}
        >
          Engineer Evidence Drawer
          <span>{drawerOpen ? "Hide" : "Show"}</span>
        </button>

        {drawerOpen && <EngineerDrawer engineer={engineer} />}
      </section>
      )}

      {activeTab === "controls" && (
        <section className="control-tab">
          <aside className="control-panel">
            <p className="label">Demo Controls</p>
            <div className="button-row">
              <button type="button" onClick={resetDemo}>
                Reset
              </button>
              <button type="button" className="primary" onClick={startDemo} disabled={isRunning}>
                Start CNC Demo
              </button>
              <button type="button" onClick={stopDemo} disabled={!isRunning}>
                Stop
              </button>
            </div>
            <p className="control-note">
              Stream introduces coupling between spindle vibration and spindle motor current after
              stable baseline cycles.
            </p>
            <div className="speed-control">
              <label htmlFor="demo-speed">
                Demo speed
                <strong>{demoSpeedMs} ms / cycle</strong>
              </label>
              <input
                id="demo-speed"
                type="range"
                min="120"
                max="1200"
                step="30"
                value={demoSpeedMs}
                onChange={updateDemoSpeed}
              />
              <div className="speed-scale">
                <span>Fast</span>
                <span>Slow</span>
              </div>
            </div>
            <div className="control-readouts">
              <Metric label="Current cycle" value={cycle} />
              <Metric label="Backend" value={backendConnected ? "connected" : "not connected"} />
              <Metric label="Last update" value={lastUpdateAt || "none"} />
              <Metric
                label="Input source"
                value={sourceMode === "csv" ? `CSV (${csvRows.length} rows)` : "Built-in demo"}
              />
            </div>
            {error && <p className="error-text">{error}</p>}
          </aside>
          <EvidenceTimeline history={history} />
        </section>
      )}

      {activeTab === "settings" && (
        <SettingsPanel
          apiBase={apiBase}
          setApiBase={setApiBase}
          sourceMode={sourceMode}
          setSourceMode={setSourceMode}
          csvRows={csvRows}
          setCsvRows={setCsvRows}
          csvName={csvName}
          setCsvName={setCsvName}
          csvError={csvError}
          setCsvError={setCsvError}
        />
      )}
    </main>
  );
}

function StatusBadge({ status, urgency }) {
  return (
    <div className={`status-badge urgency-${urgency}`}>
      <span>{urgency}</span>
      <strong>{status}</strong>
    </div>
  );
}

function OperatorAlert({ operator, status, direction, urgency }) {
  const topSignals = operator.where?.top_signals || [];
  const relationship = operator.where?.top_relationship_pair || [];
  const subsystems = operator.where_to_look?.subsystems || [];
  const primarySummary =
    operator.plain_english?.what_this_means || operatorMeaning(status, operator);
  const relationshipCopy =
    relationship.length === 2
      ? `${relationship[0]} and ${relationship[1]} are moving together in a way they normally do not.`
      : "These signals are moving together in a way they normally do not.";
  const inspectCopy =
    subsystems.length > 0
      ? `Inspect ${subsystems.join(" and ")}.`
      : "Inspection target will appear after confirmed structural evidence.";

  return (
    <div className="operator-alert">
      <div className="alert-main">
        <div className="alert-kicker">
          <p className="label">Main Operator Alert</p>
          <span>Asset CNC-01</span>
        </div>
        <h3>{primarySummary}</h3>
        <p>{relationshipCopy}</p>
        <p className="claim-boundary">
          This does not identify an exact failed component or failure time.
        </p>
      </div>
      <div className="alert-grid">
        <Metric label="Status" value={status} />
        <Metric label="Direction" value={direction} />
        <Metric label="Urgency" value={urgency} />
        <Metric
          label="Recommended action"
          value={operator.recommended_next_step || "CONTINUE_MONITORING"}
        />
        <div className="metric primary-relationship">
          <span>Primary relationship</span>
          <div>
            {(relationship.length > 0 ? relationship : ["Awaiting relationship evidence"]).map(
              (signal) => (
                <strong key={signal}>{signal}</strong>
              ),
            )}
          </div>
        </div>
        <div className="metric primary-signals">
          <span>Primary signals</span>
          <div>
            {(topSignals.length > 0 ? topSignals : ["Awaiting signal evidence"]).map((signal) => (
              <strong key={signal}>{signal}</strong>
            ))}
          </div>
        </div>
      </div>
      <div className="inspect-row">
        <span>Where to inspect</span>
        <p>{inspectCopy}</p>
        <div>
          {(subsystems.length > 0 ? subsystems : ["Awaiting confirmed evidence"]).map((item) => (
            <strong key={item}>{item}</strong>
          ))}
        </div>
      </div>
    </div>
  );
}

function StructuralStateStrip({ metrics, evidence }) {
  return (
    <section className="state-strip">
      <Metric label="Drift Score" value={formatNumber(metrics.drift_score)} />
      <Metric label="Relational Stability" value={formatNumber(metrics.relational_stability)} />
      <Metric label="Covariance Shift" value={formatNumber(metrics.covariance_shift)} />
      <Metric label="Active Evidence Families" value={evidence.active_families ?? "none"} />
    </section>
  );
}

function LiveRelationshipGraph({ operator, relationships, status, metrics }) {
  const topPairNames = operator.where?.top_relationship_pair || [];
  const topSignals = operator.where?.top_signals || [];
  const topRelationship =
    relationships.find((relationship) => sameNamePair(relationship.pair, topPairNames)) ||
    relationships[0];
  const activePair = topRelationship?.pair || [];
  const shift = Number(metrics?.covariance_shift || 0);
  const confirmed = status === "CONFIRMED_CHANGE" || status === "CONFIRMED_CHANGE_HELD";
  const intensity = confirmed ? Math.min(1, Math.max(0.45, shift / 1.6)) : 0.18;
  const activeEdge = activePair.length === 2 ? getEdge(activePair[0], activePair[1]) : null;

  return (
    <section className="relationship-graph panel-block">
      <div className="section-heading">
        <p className="label">Live Relationship Graph</p>
        <span>edge intensity {formatNumber(shift)}</span>
      </div>
      <svg viewBox="0 0 300 210" role="img" aria-label="CNC signal relationship graph">
        {activeEdge && (
          <line
            x1={activeEdge.x1}
            y1={activeEdge.y1}
            x2={activeEdge.x2}
            y2={activeEdge.y2}
            stroke={`rgba(216, 184, 106, ${intensity})`}
            strokeWidth={3 + intensity * 7}
            strokeLinecap="round"
          />
        )}
        {GRAPH_NODES.map((node) => {
          const label = SIGNAL_LABELS[node.id];
          const active = activePair.includes(node.id);
          const topSignal = topSignals.includes(label);
          return (
            <g
              key={node.id}
              className={`graph-node ${active ? "active" : ""} ${topSignal ? "top-signal" : ""}`}
            >
              <circle cx={node.x} cy={node.y} r={active ? 18 : 14} />
              <text x={node.x} y={node.y + 32}>
                {label}
              </text>
            </g>
          );
        })}
      </svg>
    </section>
  );
}

function EvidenceTimeline({ history }) {
  const firstConfirmedIndex = history.findIndex((item) =>
    ["CONFIRMED_CHANGE", "CONFIRMED_CHANGE_HELD"].includes(item.output.operator?.status),
  );
  const driftValues = history
    .map((item) => item.output.engineer?.structural_metrics?.drift_score)
    .filter((value) => typeof value === "number" && !Number.isNaN(value));
  const maxDrift = Math.max(1, ...driftValues);
  const points = history
    .map((item, index) => {
      const value = item.output.engineer?.structural_metrics?.drift_score;
      if (typeof value !== "number" || Number.isNaN(value)) return null;
      const x = history.length <= 1 ? 0 : (index / (history.length - 1)) * 100;
      const y = 42 - (value / maxDrift) * 38;
      return `${x},${y}`;
    })
    .filter(Boolean)
    .join(" ");

  return (
    <section className="timeline panel-block">
      <div className="section-heading">
        <p className="label">Evidence Timeline</p>
        <span>last {history.length} cycles</span>
      </div>
      <div className="status-bars">
        {history.length === 0 && <em>Waiting for stream data</em>}
        {history.map((item, index) => (
          <span
            key={item.cycle}
            className={`timeline-bar ${statusClass(item.output.operator?.status)} ${
              index === firstConfirmedIndex ? "first-confirmed" : ""
            }`}
            title={`cycle ${item.cycle}: ${item.output.operator?.status}`}
          />
        ))}
      </div>
      <svg className="drift-chart" viewBox="0 0 100 48" preserveAspectRatio="none">
        <polyline points={points} fill="none" stroke="#d8b86a" strokeWidth="2" />
      </svg>
    </section>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function operatorSummary(status, operator) {
  if (operator.what_is_happening?.summary) {
    return operator.what_is_happening.summary;
  }

  if (status === "TRANSIENT") {
    return "Baseline established. No confirmed structural change.";
  }

  if (status === "INITIALIZING") {
    return "Baseline is being established.";
  }

  return "Structural evidence is being evaluated.";
}

function operatorMeaning(status, operator) {
  if (operator.plain_english?.what_this_means) {
    return operator.plain_english.what_this_means;
  }

  if (status === "TRANSIENT") {
    return "Current behavior remains within transient variation around the learned baseline.";
  }

  if (status === "INITIALIZING") {
    return "Neraium is collecting enough cycles to compare current behavior against baseline.";
  }

  return "Persistent structural evidence is present, but the operator summary is still being formed.";
}

function watchNextCopy(watchNext) {
  if (!watchNext) {
    return "No confirmed watch items yet.";
  }

  const signals = watchNext.signals || [];
  const relationship = watchNext.relationship || [];
  const direction = watchNext.direction || "not established";

  if (relationship.length >= 2) {
    return `Watch ${relationship[0]} and ${relationship[1]} as trajectory remains ${direction}.`;
  }

  if (signals.length > 0) {
    return `Watch ${signals.join(" and ")} as trajectory remains ${direction}.`;
  }

  return `Watch trajectory direction as it remains ${direction}.`;
}

function EngineerDrawer({ engineer }) {
  const metrics = engineer.structural_metrics || {};
  const evidence = engineer.evidence || {};
  const relationships = engineer.contributors?.top_relationships || [];
  const trajectory = engineer.trajectory_metrics || {};

  return (
    <div className="drawer-body">
      <div className="evidence-grid">
        <Metric label="Drift score" value={formatNumber(metrics.drift_score)} />
        <Metric label="Relational stability" value={formatNumber(metrics.relational_stability)} />
        <Metric label="Covariance shift" value={formatNumber(metrics.covariance_shift)} />
        <Metric label="Active families" value={evidence.active_families ?? "none"} />
      </div>

      <div className="technical-block">
        <span>Evidence families</span>
        <pre>{JSON.stringify(evidence.supporting_families || {}, null, 2)}</pre>
      </div>

      <div className="technical-block">
        <span>Top relationships</span>
        <div className="relationship-list">
          {relationships.length === 0 && <p>No relationship evidence yet.</p>}
          {relationships.map((relationship) => (
            <div className="relationship-row" key={relationship.pair.join("-")}>
              <strong>{relationship.pair.join(" / ")}</strong>
              <span>cov {formatNumber(relationship.covariance_shift_norm)}</span>
              <span>corr {formatNumber(relationship.correlation_shift)}</span>
              <span>current {formatNumber(relationship.current_correlation)}</span>
              <span>baseline {formatNumber(relationship.baseline_correlation)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="technical-block drawer-columns">
        <div>
          <span>Internal pattern</span>
          <pre>{engineer.pattern?.type || "none"}</pre>
        </div>
        <div>
          <span>Rule triggered</span>
          <pre>{engineer.pattern?.rule_triggered || "none"}</pre>
        </div>
      </div>

      <div className="technical-block">
        <span>Trajectory metrics</span>
        <pre>{JSON.stringify(trajectory, null, 2)}</pre>
      </div>
    </div>
  );
}

function SettingsPanel({
  apiBase,
  setApiBase,
  sourceMode,
  setSourceMode,
  csvRows,
  setCsvRows,
  csvName,
  setCsvName,
  csvError,
  setCsvError,
}) {
  async function handleCsvUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const rows = parseCsvSignals(text);
      setCsvRows(rows);
      setCsvName(file.name);
      setCsvError("");
      setSourceMode("csv");
    } catch (err) {
      setCsvRows([]);
      setCsvName("");
      setCsvError(err.message);
    }
  }

  return (
    <section className="settings-grid">
      <article className="settings-panel">
        <p className="label">Backend API</p>
        <label className="field-label" htmlFor="api-base">
          API base URL
        </label>
        <input
          id="api-base"
          value={apiBase}
          onChange={(event) => setApiBase(event.target.value.trim())}
          placeholder="http://127.0.0.1:8000"
        />
        <p className="control-note">
          Use <strong>/api</strong> when running through the Vite proxy, or a full backend URL
          when calling FastAPI directly.
        </p>
      </article>

      <article className="settings-panel">
        <p className="label">Input Source</p>
        <div className="source-toggle">
          <button
            type="button"
            className={sourceMode === "demo" ? "active" : ""}
            onClick={() => setSourceMode("demo")}
          >
            Built-in demo
          </button>
          <button
            type="button"
            className={sourceMode === "csv" ? "active" : ""}
            onClick={() => setSourceMode("csv")}
            disabled={csvRows.length === 0}
          >
            Loaded CSV
          </button>
        </div>

        <label className="file-drop">
          <span>Load CNC CSV</span>
          <input type="file" accept=".csv,text/csv" onChange={handleCsvUpload} />
        </label>

        <div className="csv-status">
          <strong>{csvName || "No CSV loaded"}</strong>
          <span>{csvRows.length > 0 ? `${csvRows.length} usable rows` : "Expected CNC signal columns"}</span>
        </div>
        {csvError && <p className="error-text">{csvError}</p>}
      </article>
    </section>
  );
}

function parseCsvSignals(text) {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length < 2) {
    throw new Error("CSV must include a header and at least one data row.");
  }

  const headers = splitCsvLine(lines[0]).map((header) => header.trim());
  const indexes = SIGNAL_NAMES.map((name) => headers.indexOf(name));
  const missing = SIGNAL_NAMES.filter((_, index) => indexes[index] === -1);

  if (missing.length > 0) {
    throw new Error(`CSV missing required columns: ${missing.join(", ")}`);
  }

  return lines.slice(1).map((line, rowIndex) => {
    const cells = splitCsvLine(line);
    const signals = {};
    SIGNAL_NAMES.forEach((name, index) => {
      const value = Number(cells[indexes[index]]);
      if (!Number.isFinite(value)) {
        throw new Error(`CSV row ${rowIndex + 2} has non-numeric value for ${name}.`);
      }
      signals[name] = value;
    });
    return signals;
  });
}

function splitCsvLine(line) {
  return line.split(",").map((cell) => cell.trim().replace(/^"|"$/g, ""));
}

function sameNamePair(rawPair, displayPair) {
  if (!rawPair || !displayPair || rawPair.length !== 2 || displayPair.length !== 2) {
    return false;
  }
  const names = rawPair.map((id) => SIGNAL_LABELS[id] || id);
  return names.every((name) => displayPair.includes(name));
}

function getEdge(sourceId, targetId) {
  const source = GRAPH_NODES.find((node) => node.id === sourceId);
  const target = GRAPH_NODES.find((node) => node.id === targetId);
  if (!source || !target) return null;
  return { x1: source.x, y1: source.y, x2: target.x, y2: target.y };
}

function statusClass(status) {
  if (status === "CONFIRMED_CHANGE" || status === "CONFIRMED_CHANGE_HELD") {
    return "confirmed";
  }
  if (status === "TRANSIENT") return "transient";
  return "initializing";
}

function formatNumber(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "none";
  return value.toFixed(2);
}

export default App;
