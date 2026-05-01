import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_NERAIUM_API_BASE || "/api";
const SIGNAL_NAMES = [
  "spindle_vibration",
  "spindle_motor_current",
  "coolant_flow_rate",
  "axis_servo_load",
  "cutting_zone_temperature",
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

async function postJson(path, payload) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

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
  const timerRef = useRef(null);
  const rngRef = useRef(createRng(42));
  const cycleRef = useRef(0);

  const operator = systemOutput.operator || { status: "INITIALIZING" };
  const engineer = systemOutput.engineer || { status: "INITIALIZING" };
  const urgency = operator.trajectory?.urgency || "low";
  const direction = operator.trajectory?.direction || "not established";
  const status = operator.status || "INITIALIZING";

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
    const output = await postJson("/reset", {});
    setSystemOutput({
      operator: { status: output.status === "reset" ? "INITIALIZING" : output.status },
      engineer: { status: output.status === "reset" ? "INITIALIZING" : output.status },
    });
  }

  async function sendCycle() {
    const currentCycle = cycleRef.current;
    const payload = {
      asset_id: "CNC-01",
      signals: demoPacket(currentCycle, rngRef.current),
    };

    const output = await postJson("/update", payload);
    setSystemOutput(output);
    setCycle(currentCycle);
    cycleRef.current = currentCycle + 1;
  }

  function startDemo() {
    if (timerRef.current) return;
    setError("");
    setIsRunning(true);
    timerRef.current = window.setInterval(() => {
      sendCycle().catch((err) => {
        setError(err.message);
        stopDemo();
      });
    }, 120);
  }

  function stopDemo() {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRunning(false);
  }

  useEffect(() => {
    return () => stopDemo();
  }, []);

  return (
    <main className="console-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Live structural evidence</p>
          <h1>Neraium Operator Console</h1>
        </div>
        <div className="cycle-readout">
          <span>Cycle</span>
          <strong>{cycle}</strong>
        </div>
      </header>

      <section className={`asset-panel ${statusTone}`}>
        <div className="asset-heading">
          <div>
            <p className="label">Asset</p>
            <h2>CNC-01</h2>
          </div>
          <StatusBadge status={status} urgency={urgency} />
        </div>

        <div className="metric-grid">
          <Metric label="Status" value={status} />
          <Metric label="Urgency" value={urgency} />
          <Metric label="Direction" value={direction} />
          <Metric
            label="Recommended action"
            value={operator.recommended_next_step || "CONTINUE_MONITORING"}
          />
        </div>

        <div className="signals-strip">
          <span>Primary signals</span>
          <div>
            {(operator.where?.top_signals || ["Awaiting signal evidence"]).map((signal) => (
              <strong key={signal}>{signal}</strong>
            ))}
          </div>
        </div>
      </section>

      <section className="story-layout">
        <article className="operator-story">
          <p className="label">Operator Story</p>
          <h3>{operator.what_is_happening?.summary || "Baseline is being established."}</h3>
          <p className="story-copy">
            {operator.plain_english?.what_this_means ||
              "Neraium is collecting enough cycles to compare current behavior against baseline."}
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
          {error && <p className="error-text">{error}</p>}
        </aside>
      </section>

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

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EngineerDrawer({ engineer }) {
  const metrics = engineer.structural_metrics || {};
  const evidence = engineer.evidence || {};
  const relationships = engineer.contributors?.top_relationships || [];

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
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function formatNumber(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "none";
  return value.toFixed(2);
}

export default App;
