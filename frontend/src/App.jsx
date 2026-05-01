import { useEffect, useRef, useState } from "react";

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

const SIGNAL_DISPLAY = {
  spindle_vibration: "Spindle Vibration",
  spindle_motor_current: "Spindle Motor Current",
  coolant_flow_rate: "Coolant Flow Rate",
  axis_servo_load: "Axis Servo Load",
  cutting_zone_temperature: "Cutting Zone Temp",
};

const GRAPH_NODES = [
  { id: "sensor_0", x: 50, y: 40 },
  { id: "sensor_1", x: 250, y: 40 },
  { id: "sensor_2", x: 50, y: 170 },
  { id: "sensor_3", x: 250, y: 170 },
  { id: "sensor_4", x: 150, y: 105 },
];

const MACHINE_LIST = [
  { id: "CNC-01", type: "5-axis mill" },
  { id: "CNC-02", type: "horizontal mill" },
  { id: "CNC-03", type: "lathe cell" },
  { id: "CNC-04", type: "grinding cell" },
];

const DEMO_INTERVALS = { slow: 1000, normal: 450, fast: 150 };

const EVIDENCE_FAMILY_LABELS = {
  sensor_deviation: "Sensor Deviation",
  relationship_shift: "Relationship Shift",
  relational_stability_change: "Relational Stability Change",
  trajectory_pressure: "Trajectory Pressure",
};

function makeInitialMachineData() {
  return Object.fromEntries(
    MACHINE_LIST.map((m) => [
      m.id,
      {
        systemOutput: {
          operator: { status: "INITIALIZING" },
          engineer: { status: "INITIALIZING" },
        },
        cycle: 0,
        history: [],
        signalHistory: Object.fromEntries(SIGNAL_NAMES.map((n) => [n, []])),
        lastSignals: null,
        lastPacket: null,
        lastUpdate: null,
      },
    ])
  );
}

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

function demoPacketCNC01(cycle, rng) {
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
  }
  return SIGNAL_NAMES.reduce((obj, name) => {
    obj[name] = signals[name];
    return obj;
  }, {});
}

function demoPacketStable(rng) {
  return SIGNAL_NAMES.reduce((obj, name) => {
    obj[name] = normal(rng, 0, 1);
    return obj;
  }, {});
}

async function postJson(path, payload, apiBase) {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`${path} failed with ${response.status}`);
  return response.json();
}

async function getJson(path, apiBase) {
  const response = await fetch(`${apiBase}${path}`);
  if (!response.ok) throw new Error(`${path} failed with ${response.status}`);
  return response.json();
}

async function doReset(apiBase, machineId = null) {
  const url = machineId
    ? `${apiBase}/reset?asset_id=${encodeURIComponent(machineId)}`
    : `${apiBase}/reset`;
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) throw new Error(`reset failed with ${response.status}`);
  return response.json();
}

function statusTone(status, urgency) {
  if (status === "CONFIRMED_CHANGE" || status === "CONFIRMED_CHANGE_HELD") {
    return urgency === "high" ? "critical" : "active";
  }
  if (status === "TRANSIENT") return "quiet";
  return "initializing";
}

function statusClass(status) {
  if (status === "CONFIRMED_CHANGE" || status === "CONFIRMED_CHANGE_HELD") return "confirmed";
  if (status === "TRANSIENT") return "transient";
  return "initializing";
}

function formatNumber(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toFixed(3);
}

// ── App ───────────────────────────────────────────────────────────────────────

function App() {
  const [view, setView] = useState("floor");
  const [selectedMachineId, setSelectedMachineId] = useState(null);
  const [machineData, setMachineData] = useState(makeInitialMachineData);
  const [machineEvents, setMachineEvents] = useState({});
  const [isRunning, setIsRunning] = useState(false);
  const [demoSpeed, setDemoSpeed] = useState("normal");
  const [error, setError] = useState("");
  const [backendConnected, setBackendConnected] = useState(false);
  const [activeTab, setActiveTab] = useState("operator");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [briefModal, setBriefModal] = useState({ open: false, data: null });
  const [noteInput, setNoteInput] = useState("");
  const [apiBase, setApiBase] = useState(API_BASE);
  const [sourceMode, setSourceMode] = useState("demo");
  const [csvRows, setCsvRows] = useState([]);
  const [csvName, setCsvName] = useState("");
  const [csvError, setCsvError] = useState("");
  const [engPacketOpen, setEngPacketOpen] = useState(false);
  const [engResponseOpen, setEngResponseOpen] = useState(false);

  const timerRef = useRef(null);
  const machineRngs = useRef(
    Object.fromEntries(MACHINE_LIST.map((m, i) => [m.id, createRng(42 + i)]))
  );
  const machineCycles = useRef(Object.fromEntries(MACHINE_LIST.map((m) => [m.id, 0])));

  // Refs so the interval callback always sees fresh values
  const apiBaseRef = useRef(apiBase);
  const sourceModeRef = useRef(sourceMode);
  const csvRowsRef = useRef(csvRows);
  const sendCyclesRef = useRef(null);

  useEffect(() => { apiBaseRef.current = apiBase; }, [apiBase]);
  useEffect(() => { sourceModeRef.current = sourceMode; }, [sourceMode]);
  useEffect(() => { csvRowsRef.current = csvRows; }, [csvRows]);

  useEffect(() => {
    let active = true;
    getJson("/health", apiBase)
      .then(() => { if (active) setBackendConnected(true); })
      .catch(() => { if (active) setBackendConnected(false); });
    return () => { active = false; };
  }, [apiBase]);

  useEffect(() => () => stopDemo(), []);

  async function sendAllCycles() {
    const base = apiBaseRef.current;
    const mode = sourceModeRef.current;
    const csv = csvRowsRef.current;

    const results = await Promise.all(
      MACHINE_LIST.map(async (machine) => {
        const cycle = machineCycles.current[machine.id];
        const rng = machineRngs.current[machine.id];
        let signals;
        if (machine.id === "CNC-01" && mode === "csv" && csv.length > 0) {
          const row = csv[cycle % csv.length];
          if (!row) return null;
          signals = row;
        } else if (machine.id === "CNC-01") {
          signals = demoPacketCNC01(cycle, rng);
        } else {
          signals = demoPacketStable(rng);
        }
        const ts = new Date().toISOString();
        const packet = { asset_id: machine.id, signals, cycle, timestamp: ts };
        const output = await postJson("/update", packet, base);
        machineCycles.current[machine.id] = cycle + 1;
        return { machineId: machine.id, cycle, output, signals, packet };
      })
    );

    const valid = results.filter(Boolean);
    if (valid.length === 0) { stopDemo(); return; }

    setBackendConnected(true);
    setMachineData((prev) => {
      const next = { ...prev };
      valid.forEach(({ machineId, cycle, output, signals, packet }) => {
        const p = prev[machineId] || { history: [], signalHistory: {} };
        const prevSig = p.signalHistory || {};
        const newSig = Object.fromEntries(
          SIGNAL_NAMES.map((name) => [
            name,
            [...(prevSig[name] || []), signals[name]].slice(-100),
          ])
        );
        next[machineId] = {
          systemOutput: output,
          cycle: cycle + 1,
          history: [...(p.history || []), { cycle, output }].slice(-100),
          signalHistory: newSig,
          lastSignals: signals,
          lastPacket: packet,
          lastUpdate: new Date().toLocaleTimeString(),
        };
      });
      return next;
    });
  }

  sendCyclesRef.current = sendAllCycles;

  function launchTimer(speed) {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = window.setInterval(() => {
      sendCyclesRef.current().catch((err) => {
        setError(err.message);
        setBackendConnected(false);
        stopDemo();
      });
    }, DEMO_INTERVALS[speed]);
  }

  function startDemo() {
    if (timerRef.current) return;
    setError("");
    setIsRunning(true);
    launchTimer(demoSpeed);
  }

  function stopDemo() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRunning(false);
  }

  function handleSpeedChange(newSpeed) {
    setDemoSpeed(newSpeed);
    if (isRunning) launchTimer(newSpeed);
  }

  async function resetAll() {
    stopDemo();
    setError("");
    await doReset(apiBase).catch(() => {});
    MACHINE_LIST.forEach((m, i) => {
      machineRngs.current[m.id] = createRng(42 + i);
      machineCycles.current[m.id] = 0;
    });
    setMachineData(makeInitialMachineData());
    setMachineEvents({});
    setBackendConnected(true);
  }

  async function resetMachine(machineId) {
    stopDemo();
    setError("");
    await doReset(apiBase, machineId).catch(() => {});
    const idx = MACHINE_LIST.findIndex((m) => m.id === machineId);
    machineRngs.current[machineId] = createRng(42 + idx);
    machineCycles.current[machineId] = 0;
    setMachineData((prev) => ({
      ...prev,
      [machineId]: {
        systemOutput: {
          operator: { status: "INITIALIZING" },
          engineer: { status: "INITIALIZING" },
        },
        cycle: 0,
        history: [],
        signalHistory: Object.fromEntries(SIGNAL_NAMES.map((n) => [n, []])),
        lastSignals: null,
        lastPacket: null,
        lastUpdate: null,
      },
    }));
    setMachineEvents((prev) => ({ ...prev, [machineId]: [] }));
  }

  async function fetchEvents(machineId) {
    try {
      const events = await getJson(`/events/${machineId}`, apiBase);
      setMachineEvents((prev) => ({ ...prev, [machineId]: events }));
    } catch (_) {}
  }

  function openMachine(machineId) {
    setSelectedMachineId(machineId);
    setView("detail");
    setActiveTab("operator");
    setDrawerOpen(false);
    fetchEvents(machineId);
  }

  async function handleAcknowledge() {
    try {
      await postJson(`/events/${selectedMachineId}/acknowledge`, {}, apiBase);
      await fetchEvents(selectedMachineId);
    } catch (err) { setError(err.message); }
  }

  async function handleAddNote() {
    if (!noteInput.trim()) return;
    try {
      await postJson(`/events/${selectedMachineId}/note`, { note: noteInput.trim() }, apiBase);
      await fetchEvents(selectedMachineId);
      setNoteInput("");
    } catch (err) { setError(err.message); }
  }

  async function handleCloseEvent() {
    try {
      await postJson(`/events/${selectedMachineId}/close`, {}, apiBase);
      await fetchEvents(selectedMachineId);
    } catch (err) { setError(err.message); }
  }

  async function handleGenerateBrief() {
    try {
      const data = await getJson(`/events/${selectedMachineId}/brief`, apiBase);
      setBriefModal({ open: true, data });
    } catch (err) {
      setBriefModal({ open: true, data: { error: err.message } });
    }
  }

  // Auto-fetch events when a confirmed change appears in the selected machine
  const selectedStatus =
    machineData[selectedMachineId]?.systemOutput?.operator?.status || "INITIALIZING";
  useEffect(() => {
    if (
      selectedMachineId &&
      (selectedStatus === "CONFIRMED_CHANGE" || selectedStatus === "CONFIRMED_CHANGE_HELD")
    ) {
      fetchEvents(selectedMachineId);
    }
  }, [selectedStatus, selectedMachineId]);

  // ── Derived state for detail view ────────────────────────────────────────
  const selectedMachine = MACHINE_LIST.find((m) => m.id === selectedMachineId);
  const selectedData = selectedMachineId ? machineData[selectedMachineId] : null;
  const selectedEvents = selectedMachineId ? (machineEvents[selectedMachineId] || []) : [];
  const openEvent = selectedEvents.find((e) => e.status === "open");
  const systemOutput = selectedData?.systemOutput || {
    operator: { status: "INITIALIZING" },
    engineer: { status: "INITIALIZING" },
  };
  const operator = systemOutput.operator || { status: "INITIALIZING" };
  const engineer = systemOutput.engineer || { status: "INITIALIZING" };
  const urgency = operator.trajectory?.urgency || "low";
  const direction = operator.trajectory?.direction || "not established";
  const status = operator.status || "INITIALIZING";
  const metrics = engineer.structural_metrics || {};
  const evidence = engineer.evidence || {};
  const relationships = engineer.contributors?.top_relationships || [];
  const tone = statusTone(status, urgency);

  // ── Shared demo controls props ────────────────────────────────────────────
  const demoCtrlProps = {
    isRunning,
    demoSpeed,
    onSpeedChange: handleSpeedChange,
    onStart: startDemo,
    onStop: stopDemo,
    onResetAll: resetAll,
    onResetMachine: resetMachine,
    backendConnected,
    error,
    sourceMode,
    csvRows,
    selectedMachineId,
    onNavigate: openMachine,
  };

  return (
    <>
      <main className="console-shell">
        {/* ── FLOOR VIEW ─────────────────────────────────────────────────── */}
        {view === "floor" && (
          <>
            <header className="topbar">
              <div>
                <p className="eyebrow">CNC manufacturing floor · structural monitoring</p>
                <h1>Neraium Manufacturing Console</h1>
              </div>
              <div className="floor-header-right">
                <span className={`backend-pill ${backendConnected ? "ok" : "err"}`}>
                  {backendConnected ? "Backend connected" : "Backend disconnected"}
                </span>
                <div className="button-row floor-btn-row">
                  <button type="button" onClick={resetAll}>Reset All</button>
                  <button
                    type="button"
                    className="primary"
                    onClick={startDemo}
                    disabled={isRunning}
                  >
                    Start Demo
                  </button>
                  <button type="button" onClick={stopDemo} disabled={!isRunning}>Stop</button>
                </div>
                <div className="speed-row">
                  {["slow", "normal", "fast"].map((s) => (
                    <button
                      key={s}
                      type="button"
                      className={`speed-btn ${demoSpeed === s ? "active" : ""}`}
                      onClick={() => handleSpeedChange(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </header>

            {error && <p className="error-text">{error}</p>}

            <section className="machine-grid">
              {MACHINE_LIST.map((machine) => {
                const d = machineData[machine.id] || {};
                const out = d.systemOutput || {};
                const op = out.operator || { status: "INITIALIZING" };
                const st = op.status || "INITIALIZING";
                const urg = op.trajectory?.urgency || "low";
                const dir = op.trajectory?.direction || "not established";
                const sum =
                  op.plain_english?.what_this_means || "Collecting baseline data.";
                const t = statusTone(st, urg);
                return (
                  <button
                    key={machine.id}
                    type="button"
                    className={`machine-card tone-${t}`}
                    onClick={() => openMachine(machine.id)}
                  >
                    <div className="machine-card-header">
                      <div>
                        <p className="label">CNC Machine</p>
                        <h2>{machine.id}</h2>
                        <p className="machine-type">{machine.type}</p>
                      </div>
                      <StatusBadge status={st} urgency={urg} />
                    </div>
                    <div className="machine-card-metrics">
                      <Metric label="Status" value={st} />
                      <Metric label="Direction" value={dir} />
                      <Metric label="Urgency" value={urg} />
                      <Metric label="Cycle" value={d.cycle || 0} />
                    </div>
                    <p className="machine-summary">{sum}</p>
                    <div className="card-open-label">Open Detail →</div>
                  </button>
                );
              })}
            </section>

            <p className="floor-demo-note">
              <span className="label">Demo</span> CNC-01 develops spindle coupling after cycle 70.
              CNC-02, CNC-03, and CNC-04 remain stable.
            </p>
          </>
        )}

        {/* ── DETAIL VIEW ────────────────────────────────────────────────── */}
        {view === "detail" && selectedMachine && (
          <>
            <header className="topbar detail-topbar">
              <div className="detail-back-group">
                <button type="button" className="back-btn" onClick={() => setView("floor")}>
                  ← Floor
                </button>
                <div>
                  <p className="eyebrow">CNC machine detail</p>
                  <h1>{selectedMachine.id}</h1>
                  <p className="machine-type">{selectedMachine.type}</p>
                </div>
              </div>
              <div className="detail-topbar-right">
                <div className="cycle-readout">
                  <span>Cycle</span>
                  <strong>{selectedData?.cycle || 0}</strong>
                </div>
                <StatusBadge status={status} urgency={urgency} />
              </div>
            </header>

            <section className={`asset-panel ${tone}`}>
              <OperatorAlert
                operator={operator}
                status={status}
                direction={direction}
                urgency={urgency}
                machineId={selectedMachineId}
              />
            </section>

            <StructuralStateStrip metrics={metrics} evidence={evidence} />

            <nav className="tabbar" aria-label="Machine detail sections">
              {[
                ["operator", "Operator"],
                ["relationships", "Relationships"],
                ["evidence", "Evidence"],
                ["engineering", "Engineering Console"],
                ["controls", "Demo"],
                ["settings", "Settings"],
              ].map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={activeTab === key ? "active" : ""}
                  onClick={() => setActiveTab(key)}
                >
                  {label}
                </button>
              ))}
            </nav>

            {/* Operator tab */}
            {activeTab === "operator" && (
              <section className="story-layout operator-only">
                <article className="operator-story">
                  <p className="label">Operator Story</p>
                  <h3>
                    {operator.what_is_happening?.summary || "Baseline is being established."}
                  </h3>
                  <p className="story-copy">
                    {operator.plain_english?.what_this_means ||
                      "Neraium is collecting enough cycles to compare current behavior against baseline."}
                  </p>

                  <div className="story-block">
                    <span>Where to look</span>
                    <ul>
                      {(operator.where_to_look?.subsystems || ["Awaiting confirmed evidence"]).map(
                        (item) => <li key={item}>{item}</li>
                      )}
                    </ul>
                  </div>

                  <div className="story-block">
                    <span>Why it matters</span>
                    <p>
                      {operator.why_it_matters?.meaning ||
                        "No structural change is confirmed yet."}
                    </p>
                  </div>

                  <div className="story-block muted">
                    <span>If ignored</span>
                    <p>
                      {operator.if_ignored?.expected_behavior ||
                        "No confirmed behavior to project."}
                    </p>
                  </div>

                  <div className="story-block muted">
                    <span>What this does not claim</span>
                    <p>
                      {operator.plain_english?.what_we_are_not_claiming ||
                        "This view does not claim a failure mode, failure time, or exact physical cause."}
                    </p>
                  </div>

                  <IncidentPanel
                    openEvent={openEvent}
                    status={status}
                    noteInput={noteInput}
                    setNoteInput={setNoteInput}
                    onAcknowledge={handleAcknowledge}
                    onAddNote={handleAddNote}
                    onClose={handleCloseEvent}
                    onBrief={handleGenerateBrief}
                  />
                </article>
              </section>
            )}

            {/* Relationships tab */}
            {activeTab === "relationships" && (
              <section className="insight-layout single-tab">
                <LiveRelationshipGraph
                  operator={operator}
                  relationships={relationships}
                  status={status}
                  metrics={metrics}
                />
                <EvidenceTimeline history={selectedData?.history || []} />
              </section>
            )}

            {/* Evidence tab */}
            {activeTab === "evidence" && (
              <section className="engineer-section">
                <button
                  type="button"
                  className="drawer-toggle"
                  onClick={() => setDrawerOpen((o) => !o)}
                >
                  Engineer Evidence Drawer
                  <span>{drawerOpen ? "Hide" : "Show"}</span>
                </button>
                {drawerOpen && <EngineerDrawer engineer={engineer} />}
              </section>
            )}

            {/* Engineering Console tab */}
            {activeTab === "engineering" && (
              <EngineeringConsole
                machine={selectedMachine}
                data={selectedData}
                engineer={engineer}
                operator={operator}
                status={status}
                packOpen={engPacketOpen}
                setPackOpen={setEngPacketOpen}
                respOpen={engResponseOpen}
                setRespOpen={setEngResponseOpen}
                demoCtrl={demoCtrlProps}
                onNavigate={openMachine}
              />
            )}

            {/* Demo / controls tab */}
            {activeTab === "controls" && (
              <section className="control-tab">
                <aside className="control-panel">
                  <p className="label">Demo Controls</p>
                  <div className="button-row">
                    <button
                      type="button"
                      onClick={() => resetMachine(selectedMachineId)}
                    >
                      Reset This Machine
                    </button>
                    <button type="button" onClick={resetAll}>
                      Reset All Machines
                    </button>
                    <button
                      type="button"
                      className="primary"
                      onClick={startDemo}
                      disabled={isRunning}
                    >
                      Start Demo
                    </button>
                    <button type="button" onClick={stopDemo} disabled={!isRunning}>
                      Stop
                    </button>
                  </div>
                  <p className="control-note">
                    CNC-01 develops spindle coupling between spindle vibration and spindle motor
                    current after cycle 70. Other machines remain stable.
                  </p>
                  <div className="control-readouts">
                    <Metric label="Current cycle" value={selectedData?.cycle || 0} />
                    <Metric
                      label="Backend"
                      value={backendConnected ? "connected" : "not connected"}
                    />
                    <Metric label="Last update" value={selectedData?.lastUpdate || "none"} />
                    <Metric
                      label="Input source"
                      value={
                        sourceMode === "csv" ? `CSV (${csvRows.length} rows)` : "Built-in demo"
                      }
                    />
                  </div>
                  {error && <p className="error-text">{error}</p>}
                </aside>
                <EvidenceTimeline history={selectedData?.history || []} />
              </section>
            )}

            {/* Settings tab */}
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
          </>
        )}
      </main>

      {briefModal.open && (
        <BriefModal
          data={briefModal.data}
          onClose={() => setBriefModal({ open: false, data: null })}
        />
      )}
    </>
  );
}

// ── Engineering Console ────────────────────────────────────────────────────────

function EngineeringConsole({
  machine,
  data,
  engineer,
  operator,
  status,
  packOpen,
  setPackOpen,
  respOpen,
  setRespOpen,
  demoCtrl,
  onNavigate,
}) {
  const history = data?.history || [];
  const signalHistory = data?.signalHistory || {};
  const lastSignals = data?.lastSignals || {};
  const lastPacket = data?.lastPacket || null;
  const cycle = data?.cycle || 0;
  const lastUpdate = data?.lastUpdate || null;

  const metrics = engineer.structural_metrics || {};
  const evidence = engineer.evidence || {};
  const families = evidence.supporting_families || {};
  const relationships = engineer.contributors?.top_relationships || [];
  const trajectory = engineer.trajectory_metrics || {};

  const driftVals = history
    .map((h) => h.output.engineer?.structural_metrics?.drift_score)
    .filter((v) => typeof v === "number");
  const stabilityVals = history
    .map((h) => h.output.engineer?.structural_metrics?.relational_stability)
    .filter((v) => typeof v === "number");
  const covVals = history
    .map((h) => h.output.engineer?.structural_metrics?.covariance_shift)
    .filter((v) => typeof v === "number");
  const velocityVals = history
    .map((h) => h.output.engineer?.trajectory_metrics?.drift_velocity)
    .filter((v) => typeof v === "number");

  return (
    <div className="eng-console">
      {/* Live Telemetry */}
      <section className="eng-section">
        <div className="eng-section-head">
          <p className="label">Live Telemetry Stream</p>
          <div className="eng-meta-row">
            <span>Machine: <strong>{machine.id}</strong></span>
            <span>Cycle: <strong>{cycle}</strong></span>
            <span>Updated: <strong>{lastUpdate || "—"}</strong></span>
            <span>Status: <strong>{status}</strong></span>
          </div>
        </div>
        <div className="eng-signal-grid">
          {SIGNAL_NAMES.map((name) => (
            <div key={name} className="eng-signal-cell">
              <span className="eng-signal-name">{SIGNAL_DISPLAY[name]}</span>
              <strong className="eng-signal-val">
                {lastSignals[name] !== undefined
                  ? lastSignals[name].toFixed(4)
                  : "—"}
              </strong>
            </div>
          ))}
        </div>
      </section>

      {/* Signal Charts */}
      <section className="eng-section">
        <p className="label">Signal Charts · last {(signalHistory[SIGNAL_NAMES[0]] || []).length} samples</p>
        <div className="eng-charts-grid">
          {SIGNAL_NAMES.map((name) => {
            const vals = signalHistory[name] || [];
            return (
              <div key={name} className="eng-chart-cell">
                <span className="eng-chart-label">{SIGNAL_DISPLAY[name]}</span>
                <MiniLineChart values={vals} color="#d8b86a" />
                <span className="eng-chart-range">
                  {vals.length > 0
                    ? `${Math.min(...vals).toFixed(2)} … ${Math.max(...vals).toFixed(2)}`
                    : "no data"}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* Structural Metrics + Evidence Families */}
      <div className="eng-split-row">
        {/* Metrics Charts */}
        <section className="eng-section eng-metrics-charts">
          <p className="label">Structural Metrics · over time</p>
          <div className="eng-metrics-grid">
            <MetricChart label="Drift Score" values={driftVals} color="#ff695f" />
            <MetricChart label="Relational Stability" values={stabilityVals} color="#6e8f7d" />
            <MetricChart label="Covariance Shift" values={covVals} color="#d8b86a" />
            <MetricChart label="Drift Velocity" values={velocityVals} color="#9dafb5" zero />
          </div>
        </section>

        {/* Evidence Families */}
        <section className="eng-section eng-families">
          <p className="label">Evidence Families</p>
          <div className="eng-family-list">
            {Object.entries(EVIDENCE_FAMILY_LABELS).map(([key, label]) => {
              const active = !!families[key];
              return (
                <div key={key} className={`eng-family-row ${active ? "family-active" : "family-inactive"}`}>
                  <span className="family-dot" />
                  <span className="family-name">{label}</span>
                  <span className="family-state">{active ? "ACTIVE" : "inactive"}</span>
                </div>
              );
            })}
          </div>
          <div className="eng-family-summary">
            <Metric label="Active families" value={evidence.active_families ?? "—"} />
            <Metric
              label="Persistence satisfied"
              value={evidence.persistence_satisfied ? "YES" : "NO"}
            />
          </div>
          <div className="eng-struct-now">
            <p className="label" style={{ marginTop: 14 }}>Current values</p>
            <Metric label="Drift score" value={formatNumber(metrics.drift_score)} />
            <Metric label="Rel. stability" value={formatNumber(metrics.relational_stability)} />
            <Metric label="Cov. shift" value={formatNumber(metrics.covariance_shift)} />
            <Metric
              label="Drift velocity"
              value={formatNumber(trajectory.drift_velocity)}
            />
          </div>
        </section>
      </div>

      {/* Relationship Table */}
      <section className="eng-section">
        <p className="label">Relationship Table</p>
        {relationships.length === 0 ? (
          <p className="eng-empty">No relationship evidence yet.</p>
        ) : (
          <div className="eng-rel-table">
            <div className="eng-rel-header">
              <span>Signal Pair</span>
              <span>Cov Shift</span>
              <span>Corr Shift</span>
              <span>Current Corr</span>
              <span>Baseline Corr</span>
            </div>
            {relationships.map((rel) => (
              <div key={rel.pair.join("-")} className="eng-rel-row">
                <span className="eng-rel-pair">{rel.pair.map((id) => SIGNAL_LABELS[id] || id).join(" / ")}</span>
                <span>{formatNumber(rel.covariance_shift_norm)}</span>
                <span>{formatNumber(rel.correlation_shift)}</span>
                <span>{formatNumber(rel.current_correlation)}</span>
                <span>{formatNumber(rel.baseline_correlation)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Raw Inspectors */}
      <div className="eng-split-row">
        <section className="eng-section">
          <button
            type="button"
            className="eng-collapsible-btn"
            onClick={() => setPackOpen((o) => !o)}
          >
            Raw Packet Inspector
            <span>{packOpen ? "▲" : "▼"}</span>
          </button>
          {packOpen && (
            <pre className="eng-json-view">
              {lastPacket ? JSON.stringify(lastPacket, null, 2) : "No packet sent yet."}
            </pre>
          )}
        </section>
        <section className="eng-section">
          <button
            type="button"
            className="eng-collapsible-btn"
            onClick={() => setRespOpen((o) => !o)}
          >
            Raw Response Inspector
            <span>{respOpen ? "▲" : "▼"}</span>
          </button>
          {respOpen && (
            <pre className="eng-json-view">
              {data?.systemOutput
                ? JSON.stringify(data.systemOutput, null, 2)
                : "No response yet."}
            </pre>
          )}
        </section>
      </div>

      {/* Demo Controls */}
      <section className="eng-section eng-demo-controls">
        <p className="label">Demo Controls</p>
        <div className="eng-demo-row">
          <div className="eng-demo-group">
            <span className="eng-demo-label">Speed</span>
            <div className="eng-speed-btns">
              {["slow", "normal", "fast"].map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`speed-btn ${demoCtrl.demoSpeed === s ? "active" : ""}`}
                  onClick={() => demoCtrl.onSpeedChange(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          <div className="eng-demo-group">
            <span className="eng-demo-label">Machine</span>
            <div className="eng-speed-btns">
              {MACHINE_LIST.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className={`speed-btn ${demoCtrl.selectedMachineId === m.id ? "active" : ""}`}
                  onClick={() => onNavigate(m.id)}
                >
                  {m.id}
                </button>
              ))}
            </div>
          </div>
          <div className="eng-demo-group">
            <span className="eng-demo-label">Actions</span>
            <div className="button-row">
              <button type="button" onClick={demoCtrl.onResetAll}>
                Reset All
              </button>
              <button
                type="button"
                className="primary"
                onClick={demoCtrl.onStart}
                disabled={demoCtrl.isRunning}
              >
                Start Demo
              </button>
              <button type="button" onClick={demoCtrl.onStop} disabled={!demoCtrl.isRunning}>
                Stop
              </button>
            </div>
          </div>
        </div>
        {demoCtrl.error && <p className="error-text">{demoCtrl.error}</p>}
        <p className="control-note">
          Backend: {demoCtrl.backendConnected ? "connected" : "disconnected"} ·
          Source: {demoCtrl.sourceMode === "csv" ? `CSV (${demoCtrl.csvRows.length} rows)` : "built-in demo"}
        </p>
      </section>
    </div>
  );
}

// ── Chart components ──────────────────────────────────────────────────────────

function MiniLineChart({ values, color = "#d8b86a" }) {
  if (!values || values.length < 2) {
    return (
      <svg viewBox="0 0 100 36" className="mini-chart-svg" preserveAspectRatio="none">
        <line x1="0" y1="18" x2="100" y2="18" stroke="#2a3b42" strokeWidth="1" />
      </svg>
    );
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * 100;
      const y = 34 - ((v - min) / range) * 32;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg viewBox="0 0 100 36" className="mini-chart-svg" preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function MetricChart({ label, values, color = "#d8b86a", zero = false }) {
  const hasData = values.length >= 2;
  let pts = "";
  if (hasData) {
    const min = zero ? Math.min(0, ...values) : Math.min(...values);
    const max = zero ? Math.max(0, ...values) : Math.max(...values);
    const range = max - min || 1;
    pts = values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * 100;
        const y = 44 - ((v - min) / range) * 40;
        return `${x},${y}`;
      })
      .join(" ");
  }

  const current = values.length > 0 ? values[values.length - 1] : null;

  return (
    <div className="metric-chart-cell">
      <div className="metric-chart-head">
        <span className="eng-chart-label">{label}</span>
        <span className="metric-chart-val">
          {current !== null ? current.toFixed(3) : "—"}
        </span>
      </div>
      <svg viewBox="0 0 100 48" className="metric-chart-svg" preserveAspectRatio="none">
        {zero && hasData && (() => {
          const min = Math.min(0, ...values);
          const max = Math.max(0, ...values);
          const range = max - min || 1;
          const zy = 44 - ((0 - min) / range) * 40;
          return <line x1="0" y1={zy} x2="100" y2={zy} stroke="#2a3b42" strokeWidth="1" />;
        })()}
        {hasData ? (
          <polyline
            points={pts}
            fill="none"
            stroke={color}
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        ) : (
          <line x1="0" y1="24" x2="100" y2="24" stroke="#2a3b42" strokeWidth="1" />
        )}
      </svg>
    </div>
  );
}

// ── Incident Panel ────────────────────────────────────────────────────────────

function IncidentPanel({ openEvent, status, noteInput, setNoteInput, onAcknowledge, onAddNote, onClose, onBrief }) {
  const hasEvent = !!openEvent;
  const isConfirmed = status === "CONFIRMED_CHANGE" || status === "CONFIRMED_CHANGE_HELD";

  return (
    <div className="incident-panel">
      <p className="label">Incident Workflow</p>
      {!hasEvent && (
        <p className="incident-none">
          {isConfirmed
            ? "Event record not yet loaded — refresh after demo confirms."
            : "No confirmed structural change recorded for this machine."}
        </p>
      )}
      {hasEvent && (
        <div className="incident-event-status">
          <span className="incident-event-id">{openEvent.event_id}</span>
          {openEvent.acknowledged && (
            <span className="incident-ack-badge">Acknowledged</span>
          )}
          <span className="incident-urgency">{openEvent.urgency}</span>
        </div>
      )}
      <div className="incident-buttons">
        <button
          type="button"
          onClick={onAcknowledge}
          disabled={!hasEvent || openEvent?.acknowledged}
        >
          Acknowledge
        </button>
        <button type="button" onClick={onClose} disabled={!hasEvent}>
          Close Event
        </button>
        <button
          type="button"
          className="primary"
          onClick={onBrief}
          disabled={!hasEvent}
        >
          Generate Brief
        </button>
      </div>
      {hasEvent && (
        <div className="note-input-row">
          <input
            type="text"
            placeholder="Add a field note…"
            value={noteInput}
            onChange={(e) => setNoteInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onAddNote()}
          />
          <button type="button" onClick={onAddNote} disabled={!noteInput.trim()}>
            Add Note
          </button>
        </div>
      )}
      {hasEvent && openEvent.notes?.length > 0 && (
        <div className="notes-list">
          <p className="label">Field Notes</p>
          {openEvent.notes.map((note, i) => (
            <div key={i} className="note-item">
              <span className="note-time">{new Date(note.at).toLocaleTimeString()}</span>
              <p>{note.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Brief Modal ───────────────────────────────────────────────────────────────

function BriefModal({ data, onClose }) {
  if (!data) return null;
  const ev = data.engineer_evidence_summary || {};

  return (
    <div className="brief-modal-overlay" onClick={onClose}>
      <div className="brief-modal" onClick={(e) => e.stopPropagation()}>
        <div className="brief-modal-header">
          <div>
            <p className="label">CNC Incident Brief</p>
            <h2>{data.machine_id || "CNC Machine"}</h2>
            {data.machine_type && <p className="machine-type">{data.machine_type}</p>}
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose}>
            ×
          </button>
        </div>

        {data.error ? (
          <p className="error-text" style={{ padding: "16px" }}>
            {data.error}
          </p>
        ) : (
          <div className="brief-body">
            <div className="brief-section">
              <span>What changed</span>
              <p>{data.what_changed}</p>
            </div>
            <div className="brief-section">
              <span>When detected</span>
              <p>
                {data.when_detected
                  ? new Date(data.when_detected).toLocaleString()
                  : "unknown"}
              </p>
            </div>
            <div className="brief-section">
              <span>Current status</span>
              <p>{data.current_status}</p>
            </div>
            <div className="brief-section">
              <span>Primary CNC signals</span>
              <div className="brief-tags">
                {(data.primary_signals || []).map((s) => (
                  <strong key={s}>{s}</strong>
                ))}
              </div>
            </div>
            <div className="brief-section">
              <span>Where to inspect</span>
              <div className="brief-tags">
                {(data.where_to_inspect || []).map((loc) => (
                  <strong key={loc}>{loc}</strong>
                ))}
              </div>
            </div>
            <div className="brief-section">
              <span>Recommended action</span>
              <p>{data.recommended_action}</p>
            </div>
            <div className="brief-section">
              <span>Engineer evidence summary</span>
              <div className="brief-evidence-grid">
                <Metric label="Drift score" value={formatNumber(ev.drift_score)} />
                <Metric label="Rel. stability" value={formatNumber(ev.relational_stability)} />
                <Metric label="Direction" value={ev.direction || "—"} />
                <Metric label="Urgency" value={ev.urgency || "—"} />
                <Metric label="Pattern" value={ev.pattern || "none"} />
                <Metric label="Cov. shift" value={formatNumber(ev.covariance_shift)} />
              </div>
            </div>
            {data.notes?.length > 0 && (
              <div className="brief-section">
                <span>Field notes</span>
                {data.notes.map((note, i) => (
                  <div key={i} className="brief-note">
                    <span className="note-time">{new Date(note.at).toLocaleTimeString()}</span>
                    <p>{note.text}</p>
                  </div>
                ))}
              </div>
            )}
            <div className="brief-disclaimer">
              <p>{data.not_claiming}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Existing components (unchanged logic) ─────────────────────────────────────

function StatusBadge({ status, urgency }) {
  return (
    <div className={`status-badge urgency-${urgency}`}>
      <span>{urgency}</span>
      <strong>{status}</strong>
    </div>
  );
}

function OperatorAlert({ operator, status, direction, urgency, machineId }) {
  const topSignals = operator.where?.top_signals || [];
  const relationship = operator.where?.top_relationship_pair || [];
  const subsystems = operator.where_to_look?.subsystems || [];
  const primarySummary =
    operator.plain_english?.what_this_means ||
    "Neraium is collecting enough cycles to compare current behavior against baseline.";
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
          <span>{machineId}</span>
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
              (signal) => <strong key={signal}>{signal}</strong>
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
    relationships.find((r) => sameNamePair(r.pair, topPairNames)) || relationships[0];
  const activePair = topRelationship?.pair || [];
  const shift = Number(metrics?.covariance_shift || 0);
  const confirmed = status === "CONFIRMED_CHANGE" || status === "CONFIRMED_CHANGE_HELD";
  const intensity = confirmed ? Math.min(1, Math.max(0.45, shift / 1.6)) : 0.18;
  const activeEdge = activePair.length === 2 ? getEdge(activePair[0], activePair[1]) : null;

  return (
    <section className="relationship-graph panel-block">
      <div className="section-heading">
        <p className="label">CNC Relationship Map</p>
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
              <text x={node.x} y={node.y + 32}>{label}</text>
            </g>
          );
        })}
      </svg>
    </section>
  );
}

function EvidenceTimeline({ history }) {
  const firstConfirmedIndex = history.findIndex((item) =>
    ["CONFIRMED_CHANGE", "CONFIRMED_CHANGE_HELD"].includes(item.output.operator?.status)
  );
  const driftValues = history
    .map((item) => item.output.engineer?.structural_metrics?.drift_score)
    .filter((v) => typeof v === "number" && !Number.isNaN(v));
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
          {relationships.map((rel) => (
            <div className="relationship-row" key={rel.pair.join("-")}>
              <strong>{rel.pair.join(" / ")}</strong>
              <span>cov {formatNumber(rel.covariance_shift_norm)}</span>
              <span>corr {formatNumber(rel.correlation_shift)}</span>
              <span>current {formatNumber(rel.current_correlation)}</span>
              <span>baseline {formatNumber(rel.baseline_correlation)}</span>
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
  apiBase, setApiBase,
  sourceMode, setSourceMode,
  csvRows, setCsvRows,
  csvName, setCsvName,
  csvError, setCsvError,
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
          onChange={(e) => setApiBase(e.target.value.trim())}
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
          <span>
            {csvRows.length > 0 ? `${csvRows.length} usable rows` : "Expected CNC signal columns"}
          </span>
        </div>
        {csvError && <p className="error-text">{csvError}</p>}
      </article>
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

// ── Utilities ─────────────────────────────────────────────────────────────────

function parseCsvSignals(text) {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length < 2) throw new Error("CSV must include a header and at least one data row.");
  const headers = splitCsvLine(lines[0]).map((h) => h.trim());
  const indexes = SIGNAL_NAMES.map((name) => headers.indexOf(name));
  const missing = SIGNAL_NAMES.filter((_, i) => indexes[i] === -1);
  if (missing.length > 0) throw new Error(`CSV missing required columns: ${missing.join(", ")}`);
  return lines.slice(1).map((line, rowIndex) => {
    const cells = splitCsvLine(line);
    const signals = {};
    SIGNAL_NAMES.forEach((name, i) => {
      const value = Number(cells[indexes[i]]);
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
  if (!rawPair || !displayPair || rawPair.length !== 2 || displayPair.length !== 2) return false;
  const names = rawPair.map((id) => SIGNAL_LABELS[id] || id);
  return names.every((name) => displayPair.includes(name));
}

function getEdge(sourceId, targetId) {
  const source = GRAPH_NODES.find((n) => n.id === sourceId);
  const target = GRAPH_NODES.find((n) => n.id === targetId);
  if (!source || !target) return null;
  return { x1: source.x, y1: source.y, x2: target.x, y2: target.y };
}

export default App;
