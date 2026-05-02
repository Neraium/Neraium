import { useEffect, useRef, useState } from "react";

// ── Constants ──────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_NERAIUM_API_BASE || "/api";

const SIGNAL_NAMES = [
  "spindle_vibration",
  "spindle_motor_current",
  "coolant_flow_rate",
  "axis_servo_load",
  "cutting_zone_temperature",
];

const SIGNAL_DISPLAY = {
  spindle_vibration: "Spindle Vibration",
  spindle_motor_current: "Spindle Motor Current",
  coolant_flow_rate: "Coolant Flow Rate",
  axis_servo_load: "Axis Servo Load",
  cutting_zone_temperature: "Cutting Zone Temp",
};

const DEMO_INTERVALS = { slow: 1000, normal: 450, fast: 150 };

const EVIDENCE_FAMILIES = [
  { key: "sensor_deviation", label: "Sensor deviation" },
  { key: "relationship_shift", label: "Relationship shift" },
  { key: "relational_stability_change", label: "Relational stability change" },
  { key: "trajectory_pressure", label: "Trajectory pressure" },
];

// ── Data ───────────────────────────────────────────────────────────────────────

function emptyMachineRecord() {
  return {
    systemOutput: {
      operator: { status: "INITIALIZING" },
      engineer: { status: "INITIALIZING" },
    },
    cycle: 0,
    history: [],
    signalHistory: Object.fromEntries(SIGNAL_NAMES.map((n) => [n, []])),
    lastSignals: null,
    lastUpdate: null,
    milestones: { baselineFormed: null, firstWatch: null, firstAlert: null },
    stateHistory: [],
    lastStatus: "INITIALIZING",
  };
}

// ── RNG + demo data ────────────────────────────────────────────────────────────

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
  return mean + std * Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

function demoPacketCNC01(cycle, rng) {
  const s = {
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
    s.spindle_vibration = coupling * shared + drift;
    s.spindle_motor_current = coupling * shared + normal(rng, 0, 0.04) + drift;
  }
  return SIGNAL_NAMES.reduce((o, n) => { o[n] = s[n]; return o; }, {});
}

function demoPacketStable(rng) {
  return SIGNAL_NAMES.reduce((o, n) => { o[n] = normal(rng, 0, 1); return o; }, {});
}

// ── HTTP ───────────────────────────────────────────────────────────────────────

async function postJson(path, payload, base) {
  const r = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

async function getJson(path, base) {
  const r = await fetch(`${base}${path}`);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

async function doReset(base, machineId = null) {
  const url = machineId
    ? `${base}/reset?asset_id=${encodeURIComponent(machineId)}`
    : `${base}/reset`;
  const r = await fetch(url, { method: "POST" });
  if (!r.ok) throw new Error(`reset → ${r.status}`);
  return r.json();
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(v, dec = 3) {
  if (typeof v !== "number" || Number.isNaN(v)) return "—";
  return v.toFixed(dec);
}

function getActionWindow(trajectory, evidence) {
  // Only show action window if diverging
  if (!trajectory || trajectory.direction !== "diverging") {
    return null;
  }

  const velocity = trajectory.drift_velocity || 0;
  const acceleration = trajectory.drift_acceleration || 0;
  const persistenceSatisfied = evidence?.persistence_satisfied ?? false;

  // Categorize based on velocity and acceleration
  let window, confidence;
  if (velocity > 0.1 && acceleration > 0.01) {
    window = "0–30 cycles";
    confidence = "high";
  } else if (velocity > 0.05) {
    window = "30–80 cycles";
    confidence = "moderate";
  } else {
    window = "80–150 cycles";
    confidence = "low";
  }

  const basis = `${
    trajectory.direction === "diverging"
      ? "Sustained divergence"
      : "System changing"
  }${persistenceSatisfied ? " with sustained evidence" : ""}`;

  return { window, confidence, basis };
}

// ── Components ──────────────────────────────────────────────────────────────────

function CovarianceChart({ engineer }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = canvas.offsetWidth * window.devicePixelRatio;
    canvas.height = canvas.offsetHeight * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    const rect = canvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;

    // Clear
    ctx.fillStyle = "#0a0e27";
    ctx.fillRect(0, 0, w, h);

    // Title
    ctx.fillStyle = "#a3e0e0";
    ctx.font = "14px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.fillText("Cross-signal covariance shift detected", 20, 25);

    // Axes
    const margin = 50;
    const plotW = w - margin * 2;
    const plotH = h - margin * 2;

    ctx.strokeStyle = "#444";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(margin, h - margin);
    ctx.lineTo(w - margin, h - margin);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(margin, margin);
    ctx.lineTo(margin, h - margin);
    ctx.stroke();

    // Axis labels
    ctx.fillStyle = "#888";
    ctx.font = "12px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Spindle Vibration", margin + plotW / 2, h - 10);
    ctx.save();
    ctx.translate(15, margin + plotH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("Spindle Motor Current", 0, 0);
    ctx.restore();

    // Sample points (mock data: baseline vs current)
    const scale = 0.3;
    const samples = 20;

    // Baseline points (blue)
    ctx.fillStyle = "rgba(70, 130, 200, 0.5)";
    for (let i = 0; i < samples; i++) {
      const x = Math.random() - 0.5;
      const y = Math.random() - 0.5;
      const px = margin + (x + 0.5) * scale * plotW;
      const py = h - margin - (y + 0.5) * scale * plotH;
      ctx.beginPath();
      ctx.arc(px, py, 2, 0, Math.PI * 2);
      ctx.fill();
    }

    // Current points (orange)
    ctx.fillStyle = "rgba(255, 140, 0, 0.7)";
    for (let i = 0; i < samples; i++) {
      const x = Math.random() - 0.4;
      const y = Math.random() + 0.1;
      const px = margin + (x + 0.5) * scale * plotW;
      const py = h - margin - (y + 0.5) * scale * plotH;
      ctx.beginPath();
      ctx.arc(px, py, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }

    // Legend
    ctx.font = "12px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.fillStyle = "#888";
    ctx.textAlign = "left";

    ctx.fillStyle = "rgba(70, 130, 200, 0.8)";
    ctx.fillRect(w - 160, 30, 12, 12);
    ctx.fillStyle = "#888";
    ctx.fillText("Baseline", w - 140, 39);

    ctx.fillStyle = "rgba(255, 140, 0, 0.8)";
    ctx.fillRect(w - 160, 50, 12, 12);
    ctx.fillStyle = "#888";
    ctx.fillText("Current", w - 140, 59);
  }, [engineer]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: "100%", display: "block" }}
    />
  );
}

function StructuralMetrics({ engineer }) {
  const rel = engineer?.contributors?.top_relationships?.[0] || {};
  const metrics = engineer?.structural_metrics || {};

  return (
    <div className="metrics-panel">
      <h3>Structural Metrics</h3>
      <div className="metric-row">
        <span className="label">Baseline correlation:</span>
        <span className="value">{fmt(rel.baseline_correlation, 3)}</span>
      </div>
      <div className="metric-row">
        <span className="label">Current correlation:</span>
        <span className="value">{fmt(rel.current_correlation, 3)}</span>
      </div>
      <div className="metric-row">
        <span className="label">Correlation shift:</span>
        <span className="value">{fmt(rel.correlation_shift, 3)}</span>
      </div>
      <div className="metric-row">
        <span className="label">Cov baseline:</span>
        <span className="value">{fmt(rel.covariance_shift_abs, 4)}</span>
      </div>
      <div className="metric-row">
        <span className="label">Cov current:</span>
        <span className="value">{fmt(rel.covariance_shift_norm, 4)}</span>
      </div>
      <div className="metric-row">
        <span className="label">Persistence satisfied:</span>
        <span className="value evidence-indicator">
          {engineer?.evidence?.persistence_satisfied ? "✓ Yes" : "— No"}
        </span>
      </div>
    </div>
  );
}

function EvidenceFamilies({ engineer }) {
  const families = engineer?.evidence?.families || {};

  return (
    <div className="evidence-panel">
      <h3>Active Evidence Families</h3>
      <div className="family-list">
        {EVIDENCE_FAMILIES.map((f) => (
          <div key={f.key} className="family-item">
            <input
              type="checkbox"
              checked={families[f.key] === true}
              readOnly
            />
            <label>{f.label}</label>
          </div>
        ))}
      </div>
    </div>
  );
}

function OperatorView({ operator, engineer }) {
  const actionWindow = getActionWindow(operator?.trajectory, engineer?.evidence);

  return (
    <div className="operator-panel">
      <div className="op-section">
        <h4>What is happening</h4>
        <p className="op-text">
          {operator?.what_is_happening?.summary ||
            "Waiting for structural change detection"}
        </p>
      </div>

      <div className="op-section">
        <h4>Where to look</h4>
        <p className="op-text">
          {operator?.where_to_look?.where_to_start ||
            "Start inspection around the top reported signals"}
        </p>
      </div>

      <div className="op-section">
        <h4>Direction</h4>
        <p className="op-text">
          {operator?.trajectory?.direction === "diverging"
            ? "System behavior moving away from baseline"
            : operator?.trajectory?.direction === "stabilizing"
            ? "System behavior moving back toward baseline"
            : operator?.trajectory?.direction === "flat"
            ? "System state remaining similar"
            : "Trajectory unclear; additional observation required"}
        </p>
      </div>

      <div className="op-section">
        <h4>Urgency</h4>
        <p className={`op-text urgency-${operator?.trajectory?.urgency || "low"}`}>
          {operator?.trajectory?.urgency || "low"}
        </p>
      </div>

      <div className="op-section">
        <h4>Recommended next step</h4>
        <p className="op-text">
          {operator?.recommended_next_step === "INSPECT_TOP_SIGNALS_AND_RELATIONSHIPS"
            ? "Inspect the top identified signals and their relationships"
            : "Continue monitoring for structural changes"}
        </p>
      </div>

      {actionWindow && (
        <div className="action-window">
          <h4>Action Window</h4>
          <div className="aw-content">
            <div className="aw-row">
              <span className="aw-label">Cycles:</span>
              <span className="aw-value">{actionWindow.window}</span>
            </div>
            <div className="aw-row">
              <span className="aw-label">Confidence:</span>
              <span className={`aw-value conf-${actionWindow.confidence}`}>
                {actionWindow.confidence}
              </span>
            </div>
            <div className="aw-basis">{actionWindow.basis}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function TelemetryStrip({ signals }) {
  return (
    <div className="telemetry-strip">
      {SIGNAL_NAMES.map((name) => {
        const val = signals?.[name] ?? 0;
        return (
          <div key={name} className="signal-item">
            <div className="signal-name">{SIGNAL_DISPLAY[name]}</div>
            <div className="signal-value">{fmt(val, 2)}</div>
          </div>
        );
      })}
    </div>
  );
}

function StateTimeline({ history }) {
  const recentStates = history.slice(-50);

  return (
    <div className="timeline-container">
      <h4>State History (last 50)</h4>
      <div className="timeline-bar">
        {recentStates.map((entry, idx) => {
          const status = entry?.output?.operator?.status || "INITIALIZING";
          let className = "state-dot";
          if (
            status === "ALERT" ||
            status === "ALERT_HELD"
          ) {
            className += " state-alert";
          } else if (status === "WATCH") {
            className += " state-watch";
          } else if (status === "STABLE") {
            className += " state-stable";
          } else {
            className += " state-init";
          }
          return (
            <div
              key={idx}
              className={className}
              title={`${entry.cycle || idx}: ${status}`}
            />
          );
        })}
      </div>
    </div>
  );
}

function EngineerDrawer({ engineer, isOpen, onToggle }) {
  const rel = engineer?.contributors?.top_relationships?.[0] || {};

  return (
    <div className={`engineer-drawer ${isOpen ? "open" : ""}`}>
      <button className="drawer-toggle" onClick={onToggle}>
        {isOpen ? "Hide" : "Show"} Engineer Metrics
      </button>
      {isOpen && (
        <div className="drawer-content">
          <div className="drawer-section">
            <h4>Structural Metrics</h4>
            <table className="metrics-table">
              <tbody>
                <tr>
                  <td>Drift score:</td>
                  <td>{fmt(engineer?.structural_drift_score, 3)}</td>
                </tr>
                <tr>
                  <td>Relational stability:</td>
                  <td>{fmt(engineer?.relational_stability_score, 3)}</td>
                </tr>
                <tr>
                  <td>Watch threshold:</td>
                  <td>{fmt(engineer?.watch_threshold, 3)}</td>
                </tr>
                <tr>
                  <td>Alert threshold:</td>
                  <td>{fmt(engineer?.alert_threshold, 3)}</td>
                </tr>
                <tr>
                  <td>Confidence:</td>
                  <td>{fmt(engineer?.confidence_score, 3)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="drawer-section">
            <h4>Trajectory Metrics</h4>
            <table className="metrics-table">
              <tbody>
                <tr>
                  <td>Drift velocity:</td>
                  <td>{fmt(engineer?.trajectory?.drift_velocity, 4)}</td>
                </tr>
                <tr>
                  <td>Drift acceleration:</td>
                  <td>{fmt(engineer?.trajectory?.drift_acceleration, 4)}</td>
                </tr>
                <tr>
                  <td>Direction:</td>
                  <td>{engineer?.trajectory?.direction || "—"}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="drawer-section">
            <h4>Evidence</h4>
            <table className="metrics-table">
              <tbody>
                <tr>
                  <td>Evidence count:</td>
                  <td>{engineer?.evidence?.evidence_count || 0}</td>
                </tr>
                <tr>
                  <td>Active families:</td>
                  <td>
                    {engineer?.evidence?.active_families?.length || 0} of{" "}
                    {EVIDENCE_FAMILIES.length}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {rel.pair && (
            <div className="drawer-section">
              <h4>Top Relationship</h4>
              <p>{rel.pair.join(" ↔ ")}</p>
              <table className="metrics-table">
                <tbody>
                  <tr>
                    <td>Baseline corr:</td>
                    <td>{fmt(rel.baseline_correlation, 3)}</td>
                  </tr>
                  <tr>
                    <td>Current corr:</td>
                    <td>{fmt(rel.current_correlation, 3)}</td>
                  </tr>
                  <tr>
                    <td>Correlation shift:</td>
                    <td>{fmt(rel.correlation_shift, 3)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DetailView({ machineData, machineId, onBack }) {
  const [engineDrawerOpen, setEngineDrawerOpen] = useState(false);

  const data = machineData;
  const operator = data?.systemOutput?.operator || {};
  const engineer = data?.systemOutput?.engineer || {};
  const status = operator.status || "INITIALIZING";

  return (
    <div className="detail-view">
      <div className="detail-header">
        <button className="back-btn" onClick={onBack}>
          ← Back
        </button>
        <div className="header-content">
          <h1>Neraium</h1>
          <h2>CNC Manufacturing Cell</h2>
          <h3>Live Structural Intelligence</h3>
        </div>
        <div className="status-badge" data-status={status}>
          {status}
        </div>
      </div>

      <div className="main-grid">
        <div className="left-panel">
          <div className="chart-section">
            <CovarianceChart engineer={engineer} />
          </div>
          <div className="metrics-section">
            <StructuralMetrics engineer={engineer} />
            <EvidenceFamilies engineer={engineer} />
          </div>
          <div className="note-section">
            <p className="note-text">
              No individual signal threshold is required. Neraium detects
              structural relationship change.
            </p>
          </div>
        </div>

        <div className="right-panel">
          <OperatorView operator={operator} engineer={engineer} />
        </div>
      </div>

      <div className="telemetry-section">
        <TelemetryStrip signals={data?.lastSignals} />
      </div>

      <div className="timeline-section">
        <StateTimeline history={data?.history || []} />
      </div>

      <div className="engineer-section">
        <EngineerDrawer
          engineer={engineer}
          isOpen={engineDrawerOpen}
          onToggle={() => setEngineDrawerOpen(!engineDrawerOpen)}
        />
      </div>
    </div>
  );
}

function FloorView({ machines, onSelectMachine }) {
  return (
    <div className="floor-view">
      <div className="floor-header">
        <h1>Neraium</h1>
        <h2>Manufacturing Floor</h2>
      </div>
      <div className="machines-grid">
        {machines.map((m) => (
          <button
            key={m.id}
            className="machine-btn"
            onClick={() => onSelectMachine(m.id)}
          >
            <div className="machine-id">{m.id}</div>
            <div className="machine-type">{m.type}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────────

const MACHINES = [
  { id: "CNC-01", type: "5-axis mill" },
  { id: "CNC-02", type: "horizontal mill" },
  { id: "CNC-03", type: "lathe cell" },
  { id: "CNC-04", type: "grinding cell" },
];

function App() {
  const [selectedMachineId, setSelectedMachineId] = useState(null);
  const [machineData, setMachineData] = useState(
    Object.fromEntries(MACHINES.map((m) => [m.id, emptyMachineRecord()]))
  );
  const [isRunning, setIsRunning] = useState(false);
  const [demoSpeed, setDemoSpeed] = useState("normal");
  const [error, setError] = useState("");
  const [backendConnected, setBackendConnected] = useState(false);
  const [apiBase, setApiBase] = useState(API_BASE);

  const timerRef = useRef(null);
  const machineRngs = useRef(
    Object.fromEntries(MACHINES.map((m, i) => [m.id, createRng(42 + i)]))
  );
  const machineCycles = useRef(Object.fromEntries(MACHINES.map((m) => [m.id, 0])));
  const apiBaseRef = useRef(apiBase);

  useEffect(() => {
    apiBaseRef.current = apiBase;
  }, [apiBase]);

  useEffect(() => {
    let active = true;
    getJson("/health", apiBase)
      .then(() => {
        if (active) setBackendConnected(true);
      })
      .catch(() => {
        if (active) setBackendConnected(false);
      });
    return () => {
      active = false;
    };
  }, [apiBase]);

  useEffect(() => {
    return () => stopDemo();
  }, []);

  async function sendAllCycles() {
    const base = apiBaseRef.current;

    const results = await Promise.all(
      MACHINES.map(async (machine) => {
        const cycle = machineCycles.current[machine.id];
        const rng = machineRngs.current[machine.id];
        let signals;
        if (machine.id === "CNC-01") {
          signals = demoPacketCNC01(cycle, rng);
        } else {
          signals = demoPacketStable(rng);
        }
        const ts = new Date().toISOString();
        const packet = { asset_id: machine.id, signals, cycle, timestamp: ts };
        const output = await postJson("/update", packet, base);
        machineCycles.current[machine.id] = cycle + 1;
        return { machineId: machine.id, cycle, output, signals };
      })
    );

    const valid = results.filter(Boolean);
    if (valid.length === 0) {
      stopDemo();
      return;
    }

    setBackendConnected(true);
    setMachineData((prev) => {
      const next = { ...prev };
      valid.forEach(({ machineId, cycle, output, signals }) => {
        const p = prev[machineId] || emptyMachineRecord();
        const newStatus = output.operator?.status || "INITIALIZING";
        const pm = p.milestones || {
          baselineFormed: null,
          firstWatch: null,
          firstAlert: null,
        };
        const milestones = { ...pm };
        if (milestones.baselineFormed === null && newStatus !== "INITIALIZING")
          milestones.baselineFormed = cycle;
        if (milestones.firstWatch === null && newStatus === "WATCH")
          milestones.firstWatch = cycle;
        if (
          milestones.firstAlert === null &&
          (newStatus === "ALERT" || newStatus === "ALERT_HELD")
        )
          milestones.firstAlert = cycle;

        next[machineId] = {
          systemOutput: output,
          cycle: cycle + 1,
          history: [...(p.history || []), { cycle, output }].slice(-100),
          lastSignals: signals,
          lastUpdate: new Date().toISOString(),
          milestones,
          lastStatus: newStatus,
        };
      });
      return next;
    });
  }

  function startDemo() {
    if (isRunning) return;
    setIsRunning(true);
    setError("");
    const interval = DEMO_INTERVALS[demoSpeed] || DEMO_INTERVALS.normal;
    timerRef.current = setInterval(() => {
      sendAllCycles().catch((err) => {
        setError(err.message);
        stopDemo();
      });
    }, interval);
  }

  function stopDemo() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRunning(false);
  }

  async function handleReset() {
    try {
      setError("");
      await doReset(apiBase, selectedMachineId || undefined);
      setMachineData(
        Object.fromEntries(MACHINES.map((m) => [m.id, emptyMachineRecord()]))
      );
      Object.keys(machineCycles.current).forEach(
        (k) => (machineCycles.current[k] = 0)
      );
      Object.keys(machineRngs.current).forEach((k) => {
        const idx = MACHINES.findIndex((m) => m.id === k);
        machineRngs.current[k] = createRng(42 + idx);
      });
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="app">
      <div className="app-controls">
        <div className="controls-left">
          <label>
            API Base:
            <input
              type="text"
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
            />
          </label>
          {!backendConnected && (
            <span className="status-offline">Backend offline</span>
          )}
        </div>
        <div className="controls-center">
          <button onClick={startDemo} disabled={isRunning}>
            Start Demo
          </button>
          <button onClick={stopDemo} disabled={!isRunning}>
            Stop Demo
          </button>
          <label>
            Speed:
            <select
              value={demoSpeed}
              onChange={(e) => setDemoSpeed(e.target.value)}
              disabled={isRunning}
            >
              <option value="slow">Slow</option>
              <option value="normal">Normal</option>
              <option value="fast">Fast</option>
            </select>
          </label>
        </div>
        <div className="controls-right">
          <button onClick={handleReset}>Reset</button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {selectedMachineId ? (
        <DetailView
          machineData={machineData[selectedMachineId]}
          machineId={selectedMachineId}
          onBack={() => setSelectedMachineId(null)}
        />
      ) : (
        <FloorView
          machines={MACHINES}
          onSelectMachine={setSelectedMachineId}
        />
      )}
    </div>
  );
}

export default App;
