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
  { id: "sensor_0", x: 60, y: 50 },
  { id: "sensor_1", x: 240, y: 50 },
  { id: "sensor_2", x: 60, y: 170 },
  { id: "sensor_3", x: 240, y: 170 },
  { id: "sensor_4", x: 150, y: 110 },
];

// All 10 possible pairs between 5 sensor nodes
const GRAPH_EDGES = (() => {
  const ids = GRAPH_NODES.map((n) => n.id);
  const edges = [];
  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) edges.push([ids[i], ids[j]]);
  }
  return edges;
})();

const MACHINE_LIST = [
  { id: "CNC-01", type: "5-axis mill" },
  { id: "CNC-02", type: "horizontal mill" },
  { id: "CNC-03", type: "lathe cell" },
  { id: "CNC-04", type: "grinding cell" },
];

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
    lastPacket: null,
    lastUpdate: null,
    milestones: { baselineFormed: null, firstDeviation: null, firstConfirmed: null },
    stateStartCycle: 0,
    lastStatus: "INITIALIZING",
  };
}

function makeInitialMachineData() {
  return Object.fromEntries(MACHINE_LIST.map((m) => [m.id, emptyMachineRecord()]));
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

function statusTone(status, urgency) {
  if (status === "ALERT" || status === "ALERT_HELD")
    return urgency === "high" ? "critical" : "active";
  if (status === "WATCH") return "quiet";
  return "initializing";
}

function statusBarClass(status) {
  if (status === "ALERT" || status === "ALERT_HELD") return "confirmed";
  if (status === "WATCH") return "transient";
  return "initializing";
}

function fmt(v, dec = 3) {
  if (typeof v !== "number" || Number.isNaN(v)) return "—";
  return v.toFixed(dec);
}

function describeCorrelationLevel(corr) {
  const a = Math.abs(corr ?? 0);
  if (a < 0.1) return "essentially independent";
  if (a < 0.3) return "weakly related";
  if (a < 0.5) return "moderately related";
  if (a < 0.75) return "fairly closely related";
  return "strongly related";
}

function getEdgeCoords(a, b) {
  const na = GRAPH_NODES.find((n) => n.id === a);
  const nb = GRAPH_NODES.find((n) => n.id === b);
  if (!na || !nb) return null;
  return { x1: na.x, y1: na.y, x2: nb.x, y2: nb.y };
}

// ── App ────────────────────────────────────────────────────────────────────────

function App() {
  const [view, setView] = useState("floor");
  const [selectedMachineId, setSelectedMachineId] = useState(null);
  const [machineData, setMachineData] = useState(makeInitialMachineData);
  const [machineEvents, setMachineEvents] = useState({});
  const [isRunning, setIsRunning] = useState(false);
  const [demoSpeed, setDemoSpeed] = useState("normal");
  const [error, setError] = useState("");
  const [backendConnected, setBackendConnected] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [engConsoleOpen, setEngConsoleOpen] = useState(false);
  const [engPacketOpen, setEngPacketOpen] = useState(false);
  const [engResponseOpen, setEngResponseOpen] = useState(false);
  const [briefModal, setBriefModal] = useState({ open: false, data: null });
  const [noteInput, setNoteInput] = useState("");
  const [apiBase, setApiBase] = useState(API_BASE);
  const [sourceMode, setSourceMode] = useState("demo");
  const [csvRows, setCsvRows] = useState([]);
  const [csvName, setCsvName] = useState("");
  const [csvError, setCsvError] = useState("");

  const timerRef = useRef(null);
  const machineRngs = useRef(
    Object.fromEntries(MACHINE_LIST.map((m, i) => [m.id, createRng(42 + i)]))
  );
  const machineCycles = useRef(Object.fromEntries(MACHINE_LIST.map((m) => [m.id, 0])));
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
        const p = prev[machineId] || emptyMachineRecord();
        const prevSig = p.signalHistory || {};
        const newSig = Object.fromEntries(
          SIGNAL_NAMES.map((name) => [
            name,
            [...(prevSig[name] || []), signals[name]].slice(-100),
          ])
        );
        const newStatus = output.operator?.status || "INITIALIZING";
        const pm = p.milestones || { baselineFormed: null, firstDeviation: null, firstConfirmed: null };
        const milestones = { ...pm };
        if (milestones.baselineFormed === null && newStatus !== "INITIALIZING")
          milestones.baselineFormed = cycle;
        if (milestones.firstDeviation === null && newStatus === "WATCH")
          milestones.firstDeviation = cycle;
        if (
          milestones.firstConfirmed === null &&
          (newStatus === "ALERT" || newStatus === "ALERT_HELD")
        )
          milestones.firstConfirmed = cycle;
        const stateStartCycle =
          newStatus !== (p.lastStatus || "INITIALIZING") ? cycle : (p.stateStartCycle ?? 0);
        next[machineId] = {
          systemOutput: output,
          cycle: cycle + 1,
          history: [...(p.history || []), { cycle, output }].slice(-100),
          signalHistory: newSig,
          lastSignals: signals,
          lastPacket: packet,
          lastUpdate: new Date().toLocaleTimeString(),
          milestones,
          stateStartCycle,
          lastStatus: newStatus,
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
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
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
    setMachineData((prev) => ({ ...prev, [machineId]: emptyMachineRecord() }));
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

  const selectedStatus =
    machineData[selectedMachineId]?.systemOutput?.operator?.status || "INITIALIZING";
  useEffect(() => {
    if (
      selectedMachineId &&
      (selectedStatus === "ALERT" || selectedStatus === "ALERT_HELD")
    ) {
      fetchEvents(selectedMachineId);
    }
  }, [selectedStatus, selectedMachineId]);

  // Derived state for selected machine
  const selectedMachine = MACHINE_LIST.find((m) => m.id === selectedMachineId);
  const selectedData = selectedMachineId ? machineData[selectedMachineId] : null;
  const selectedEvents = selectedMachineId ? (machineEvents[selectedMachineId] || []) : [];
  const openEvent = selectedEvents.find((e) => e.status === "open");
  const sysOut = selectedData?.systemOutput || {
    operator: { status: "INITIALIZING" },
    engineer: { status: "INITIALIZING" },
  };
  const operator = sysOut.operator || { status: "INITIALIZING" };
  const engineer = sysOut.engineer || { status: "INITIALIZING" };
  const urgency = operator.trajectory?.urgency || "low";
  const direction = operator.trajectory?.direction || "not established";
  const status = operator.status || "INITIALIZING";
  const history = selectedData?.history || [];
  const firstConfirmedIdx = history.findIndex(
    (h) =>
      h.output.operator?.status === "ALERT" ||
      h.output.operator?.status === "ALERT_HELD"
  );

  const demoCtrl = {
    isRunning, demoSpeed,
    onSpeedChange: handleSpeedChange,
    onStart: startDemo, onStop: stopDemo,
    onResetAll: resetAll, onResetMachine: resetMachine,
    backendConnected, error, sourceMode, csvRows,
    selectedMachineId,
  };

  // ── Floor view ────────────────────────────────────────────────────────────
  if (view === "floor") {
    return (
      <>
        <main className="console-shell">
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
                <button type="button" className="primary" onClick={startDemo} disabled={isRunning}>
                  Start Demo
                </button>
                <button type="button" onClick={stopDemo} disabled={!isRunning}>Stop</button>
              </div>
              <div className="speed-row">
                {["slow", "normal", "fast"].map((s) => (
                  <button
                    key={s} type="button"
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
              const op = d.systemOutput?.operator || { status: "INITIALIZING" };
              const st = op.status || "INITIALIZING";
              const urg = op.trajectory?.urgency || "low";
              const dir = op.trajectory?.direction || "not established";
              const sum = op.plain_english?.what_this_means || "Collecting baseline data.";
              return (
                <button
                  key={machine.id} type="button"
                  className={`machine-card tone-${statusTone(st, urg)}`}
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
        </main>
        {briefModal.open && (
          <BriefModal data={briefModal.data} onClose={() => setBriefModal({ open: false, data: null })} />
        )}
      </>
    );
  }

  // ── V4 Detail view ────────────────────────────────────────────────────────
  return (
    <>
      <div className="v4-shell">
        <header className="v4-header">
          <div className="v4-header-left">
            <button type="button" className="back-btn" onClick={() => setView("floor")}>
              ← Floor
            </button>
            <div>
              <p className="eyebrow">CNC manufacturing · structural monitoring</p>
              <span className="v4-title">Neraium</span>
            </div>
          </div>
          <div className="v4-header-right">
            <span className={`backend-pill ${backendConnected ? "ok" : "err"}`}>
              {backendConnected ? "● connected" : "○ disconnected"}
            </span>
            {isRunning && <span className="running-pill">● demo running</span>}
            {selectedData?.lastUpdate && (
              <span className="update-pill">updated {selectedData.lastUpdate}</span>
            )}
          </div>
        </header>

        <div className="v4-layout">
          <MachineSidebar
            machineData={machineData}
            selectedMachineId={selectedMachineId}
            onSelect={openMachine}
          />

          <main className="v4-main">
            {!selectedMachine ? (
              <div className="v4-select-prompt">
                <p>Select a CNC machine from the sidebar.</p>
              </div>
            ) : (
              <>
                <TemporalRibbon
                  milestones={selectedData?.milestones}
                  currentCycle={selectedData?.cycle || 0}
                  currentStatus={status}
                  stateStartCycle={selectedData?.stateStartCycle ?? 0}
                />

                <MainAlertCard
                  operator={operator}
                  engineer={engineer}
                  status={status}
                  urgency={urgency}
                  direction={direction}
                  machineId={selectedMachineId}
                  machineType={selectedMachine.type}
                />

                <div className="v4-two-col">
                  <WhatChangedPanel engineer={engineer} />
                  <WhyFlaggedPanel engineer={engineer} />
                </div>

                <UrgencyExplanation operator={operator} engineer={engineer} />

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

                <div className="v4-two-col">
                  <EnhancedRelationshipMap
                    operator={operator}
                    engineer={engineer}
                    status={status}
                  />
                  <EngineerChartsSection
                    history={history}
                    firstConfirmedIdx={firstConfirmedIdx}
                  />
                </div>

                <section className="v4-collapsible-section">
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

                <section className="v4-collapsible-section">
                  <button
                    type="button"
                    className="drawer-toggle"
                    onClick={() => setEngConsoleOpen((o) => !o)}
                  >
                    Engineering Console — Technical View
                    <span>{engConsoleOpen ? "Hide" : "Show"}</span>
                  </button>
                  {engConsoleOpen && (
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
                      demoCtrl={demoCtrl}
                      onNavigate={openMachine}
                    />
                  )}
                </section>

                <DemoControlsSection
                  demoCtrl={demoCtrl}
                  selectedData={selectedData}
                  selectedMachineId={selectedMachineId}
                  onNavigate={openMachine}
                  apiBase={apiBase}
                  setApiBase={setApiBase}
                  sourceMode={sourceMode}
                  setSourceMode={setSourceMode}
                  setCsvRows={setCsvRows}
                  setCsvName={setCsvName}
                  setCsvError={setCsvError}
                  csvRows={csvRows}
                  csvName={csvName}
                  csvError={csvError}
                  onResetMachine={() => resetMachine(selectedMachineId)}
                />
              </>
            )}
          </main>
        </div>
      </div>

      {briefModal.open && (
        <BriefModal
          data={briefModal.data}
          onClose={() => setBriefModal({ open: false, data: null })}
        />
      )}
    </>
  );
}

// ── MachineSidebar ─────────────────────────────────────────────────────────────

function MachineSidebar({ machineData, selectedMachineId, onSelect }) {
  return (
    <aside className="v4-sidebar">
      <p className="label sidebar-head-label">Manufacturing Floor</p>
      {MACHINE_LIST.map((machine) => {
        const d = machineData[machine.id] || {};
        const op = d.systemOutput?.operator || { status: "INITIALIZING" };
        const st = op.status || "INITIALIZING";
        const urg = op.trajectory?.urgency || "low";
        const sum = op.plain_english?.what_this_means || "Collecting baseline data.";
        const tone = statusTone(st, urg);
        const selected = selectedMachineId === machine.id;
        return (
          <button
            key={machine.id}
            type="button"
            className={`sidebar-machine tone-${tone} ${selected ? "sidebar-selected" : ""}`}
            onClick={() => onSelect(machine.id)}
          >
            <div className="sidebar-machine-row">
              <span className={`sidebar-dot tone-dot-${tone}`} />
              <div className="sidebar-machine-info">
                <span className="sidebar-machine-id">{machine.id}</span>
                <span className="sidebar-machine-type">{machine.type}</span>
              </div>
              <span className={`sidebar-urg sidebar-urg-${urg}`}>{urg}</span>
            </div>
            <p className="sidebar-machine-sum">{sum.slice(0, 72)}{sum.length > 72 ? "…" : ""}</p>
            <div className="sidebar-machine-footer">
              <span className="sidebar-status">{st}</span>
              {d.cycle > 0 && <span className="sidebar-cycle">cycle {d.cycle}</span>}
            </div>
          </button>
        );
      })}
    </aside>
  );
}

// ── TemporalRibbon ─────────────────────────────────────────────────────────────

function TemporalRibbon({ milestones, currentCycle, currentStatus, stateStartCycle }) {
  const m = milestones || { baselineFormed: null, firstDeviation: null, firstConfirmed: null };
  const cyclesInState = Math.max(0, currentCycle - stateStartCycle - 1);

  const steps = [
    {
      key: "init",
      label: "Baseline formed",
      note: "30-cycle window complete",
      cycle: m.baselineFormed,
      reached: m.baselineFormed !== null,
    },
    {
      key: "dev",
      label: "First structural change",
      note: "Initial transient detected",
      cycle: m.firstDeviation,
      reached: m.firstDeviation !== null,
    },
    {
      key: "conf",
      label: "Confirmed change",
      note: "Multi-family evidence met",
      cycle: m.firstConfirmed,
      reached: m.firstConfirmed !== null,
    },
    {
      key: "now",
      label: "You are here",
      note: `${cyclesInState} cycle${cyclesInState !== 1 ? "s" : ""} in ${currentStatus}`,
      cycle: currentCycle,
      reached: true,
      current: true,
    },
  ];

  return (
    <section className="temporal-ribbon">
      {steps.map((step, i) => (
        <div
          key={step.key}
          className={`ribbon-step ${step.reached ? "step-reached" : "step-pending"} ${step.current ? "step-current" : ""}`}
        >
          {i > 0 && <div className={`ribbon-connector ${steps[i - 1].reached ? "conn-reached" : "conn-pending"}`} />}
          <div className="ribbon-dot-wrap">
            <span className="ribbon-dot" />
          </div>
          <div className="ribbon-text">
            <span className="ribbon-label">{step.label}</span>
            {step.reached && step.cycle !== null ? (
              <span className="ribbon-cycle">Cycle {step.cycle}</span>
            ) : (
              <span className="ribbon-cycle ribbon-pending">Not reached</span>
            )}
            <span className="ribbon-note">{step.note}</span>
          </div>
        </div>
      ))}
    </section>
  );
}

// ── MainAlertCard ──────────────────────────────────────────────────────────────

function MainAlertCard({ operator, engineer, status, urgency, direction, machineId, machineType }) {
  const topSignals = operator.where?.top_signals || [];
  const relationship = operator.where?.top_relationship_pair || [];
  const subsystems = operator.where_to_look?.subsystems || [];
  const summary =
    operator.plain_english?.what_this_means ||
    "Collecting baseline data. Establishing normal operating behaviour.";
  const recommendedAction = operator.recommended_next_step || "CONTINUE_MONITORING";
  const isConfirmed = status === "ALERT" || status === "ALERT_HELD";
  const tone = statusTone(status, urgency);

  return (
    <section className={`v4-alert-card tone-${tone}`}>
      <div className="alert-card-top">
        <div className="alert-card-identity">
          <p className="label">CNC Machine</p>
          <div className="alert-card-id-row">
            <h2 className="alert-machine-id">{machineId}</h2>
            <span className="alert-machine-type">{machineType}</span>
          </div>
        </div>
        <StatusBadge status={status} urgency={urgency} />
      </div>

      <h3 className="alert-summary">{summary}</h3>

      {isConfirmed && relationship.length === 2 && (
        <p className="alert-relationship-note">
          {relationship[0]} and {relationship[1]} are moving together in a way they
          normally do not.
        </p>
      )}

      <div className="alert-meta-row">
        <div className="alert-meta-item">
          <span>Direction</span>
          <strong>{direction}</strong>
        </div>
        <div className="alert-meta-item">
          <span>Urgency</span>
          <strong>{urgency}</strong>
        </div>
        <div className="alert-meta-item">
          <span>Action</span>
          <strong>{recommendedAction}</strong>
        </div>
      </div>

      {isConfirmed && (
        <div className="alert-card-bottom">
          <div className="alert-card-where">
            <span>Primary relationship</span>
            <div className="alert-tags">
              {relationship.length > 0
                ? relationship.map((s) => <strong key={s}>{s}</strong>)
                : <span className="muted-text">Awaiting relationship evidence</span>}
            </div>
          </div>
          <div className="alert-card-inspect">
            <span>Where to inspect</span>
            <div className="alert-tags">
              {subsystems.length > 0
                ? subsystems.map((s) => <strong key={s}>{s}</strong>)
                : <span className="muted-text">Awaiting confirmed evidence</span>}
            </div>
          </div>
        </div>
      )}

      <p className="alert-boundary">
        This does not identify an exact failed component or failure time.
      </p>
    </section>
  );
}

// ── WhatChangedPanel ───────────────────────────────────────────────────────────

function WhatChangedPanel({ engineer }) {
  const rels = engineer.contributors?.top_relationships || [];
  const top = rels[0];

  if (!top) {
    return (
      <section className="v4-panel what-changed-panel">
        <p className="label">What Changed</p>
        <p className="panel-empty">No relationship evidence confirmed yet.</p>
      </section>
    );
  }

  const pair = top.pair.map((id) => SIGNAL_LABELS[id] || id);
  const baseline = top.baseline_correlation ?? null;
  const current = top.current_correlation ?? null;
  const shift = top.correlation_shift ?? null;
  const covShift = top.covariance_shift_norm ?? null;

  const shiftDir = shift !== null && shift > 0 ? "strengthened" : "weakened";
  const baselineDesc = baseline !== null ? describeCorrelationLevel(baseline) : "unknown";
  const currentDesc = current !== null ? describeCorrelationLevel(current) : "unknown";

  return (
    <section className="v4-panel what-changed-panel">
      <p className="label">What Changed</p>
      <p className="change-pair-label">{pair.join(" / ")}</p>

      <div className="change-comparison">
        <div className="change-side change-before">
          <span className="change-era">Baseline</span>
          <p className="change-desc">
            These signals were <strong>{baselineDesc}</strong>.
          </p>
          <span className="change-val">{fmt(baseline, 3)}</span>
        </div>
        <div className="change-arrow">→</div>
        <div className="change-side change-after">
          <span className="change-era">Current</span>
          <p className="change-desc">
            These signals are now <strong>{currentDesc}</strong>.
          </p>
          <span className="change-val">{fmt(current, 3)}</span>
        </div>
      </div>

      <p className="change-summary">
        The relationship between these signals has <strong>{shiftDir}</strong> since baseline.
      </p>

      <div className="change-metric-row">
        <Metric label="Correlation shift" value={fmt(shift, 3)} />
        <Metric label="Covariance shift" value={fmt(covShift, 3)} />
      </div>
    </section>
  );
}

// ── WhyFlaggedPanel ────────────────────────────────────────────────────────────

function WhyFlaggedPanel({ engineer }) {
  const evidence = engineer.evidence || {};
  const families = evidence.supporting_families || {};
  const active = evidence.active_families ?? 0;
  const persisted = evidence.persistence_satisfied;

  return (
    <section className="v4-panel why-flagged-panel">
      <p className="label">Why This Was Flagged</p>
      <div className="flagged-list">
        {EVIDENCE_FAMILIES.map(({ key, label }) => {
          const on = !!families[key];
          return (
            <div key={key} className={`flagged-row ${on ? "flagged-on" : "flagged-off"}`}>
              <span className="flagged-check">{on ? "✓" : "–"}</span>
              <span className="flagged-label">{label}</span>
              <span className="flagged-state">{on ? "Active" : "Not active"}</span>
            </div>
          );
        })}
        <div className={`flagged-row ${persisted ? "flagged-on" : "flagged-off"} flagged-persist`}>
          <span className="flagged-check">{persisted ? "✓" : "–"}</span>
          <span className="flagged-label">Persistence satisfied</span>
          <span className="flagged-state">{persisted ? "Active" : "Not active"}</span>
        </div>
      </div>
      <div className="flagged-count">
        <strong>{active}</strong>
        <span> of 4 evidence families active</span>
      </div>
    </section>
  );
}

// ── UrgencyExplanation ─────────────────────────────────────────────────────────

function UrgencyExplanation({ operator, engineer }) {
  const urgency = operator.trajectory?.urgency || "low";
  const direction = operator.trajectory?.direction || "not established";
  const evidence = engineer.evidence || {};
  const metrics = engineer.structural_metrics || {};
  const activeFamilies = evidence.active_families ?? 0;
  const persisted = evidence.persistence_satisfied;
  const drift = metrics.drift_score;
  const isConfirmed =
    operator.status === "ALERT" || operator.status === "ALERT_HELD";

  if (!isConfirmed) {
    return (
      <section className="v4-panel urgency-panel">
        <p className="label">Urgency</p>
        <p className="panel-empty">
          Urgency assessment is established after structural change is confirmed.
        </p>
      </section>
    );
  }

  function rationale() {
    if (urgency === "high") {
      if (direction === "diverging" && persisted)
        return "Drift is increasing across multiple evidence families and has persisted for several cycles. Structural behaviour continues to move away from baseline.";
      return "Structural behaviour has moved significantly from baseline with evidence across multiple families.";
    }
    if (urgency === "medium")
      return "Structural change is confirmed and stable. Behaviour has not continued to worsen significantly since confirmation.";
    return "Structural change is confirmed but within early-stage levels. Monitor for progression.";
  }

  return (
    <section className="v4-panel urgency-panel">
      <div className="urgency-head">
        <p className="label">Urgency</p>
        <span className={`urgency-badge urg-${urgency}`}>{urgency.toUpperCase()}</span>
      </div>
      <p className="urgency-rationale">{rationale()}</p>
      <div className="urgency-factors">
        <div className="urgency-factor">
          <span>Direction</span>
          <strong>{direction}</strong>
        </div>
        <div className="urgency-factor">
          <span>Persistence</span>
          <strong>{persisted ? "Satisfied" : "Not satisfied"}</strong>
        </div>
        <div className="urgency-factor">
          <span>Active families</span>
          <strong>{activeFamilies} / 4</strong>
        </div>
        {typeof drift === "number" && (
          <div className="urgency-factor">
            <span>Drift score</span>
            <strong>{drift.toFixed(2)}</strong>
          </div>
        )}
      </div>
      <p className="urgency-boundary">
        This indicates current structural behaviour is{" "}
        {direction === "diverging"
          ? "continuing to move away from baseline"
          : "at a structurally changed state"}
        . This does not identify a failure time or exact cause.
      </p>
    </section>
  );
}

// ── EnhancedRelationshipMap ────────────────────────────────────────────────────

function EnhancedRelationshipMap({ operator, engineer, status }) {
  const topPairNames = operator.where?.top_relationship_pair || [];
  const rels = engineer.contributors?.top_relationships || [];
  const topRel =
    rels.find((r) => {
      const names = r.pair.map((id) => SIGNAL_LABELS[id] || id);
      return names.every((n) => topPairNames.includes(n));
    }) || rels[0];

  const activePair = topRel?.pair || [];
  const covShift = topRel?.covariance_shift_norm ?? 0;
  const confirmed = status === "ALERT" || status === "ALERT_HELD";
  const intensity = confirmed ? Math.min(1, Math.max(0.4, covShift / 1.4)) : 0;
  const activeStrokeW = 2 + intensity * 9;

  return (
    <section className="v4-panel rel-map-panel">
      <div className="panel-head-row">
        <p className="label">CNC Relationship Map</p>
        {activePair.length === 2 && confirmed && (
          <span className="rel-map-active-label">
            {activePair.map((id) => SIGNAL_LABELS[id] || id).join(" / ")}
          </span>
        )}
      </div>
      <svg viewBox="0 0 300 220" role="img" aria-label="CNC signal relationship graph" className="rel-map-svg">
        {/* All background edges */}
        {GRAPH_EDGES.map(([a, b]) => {
          const c = getEdgeCoords(a, b);
          if (!c) return null;
          const isActive =
            (activePair.includes(a) && activePair.includes(b)) && confirmed;
          return (
            <line
              key={`${a}-${b}`}
              x1={c.x1} y1={c.y1} x2={c.x2} y2={c.y2}
              stroke={
                isActive
                  ? `rgba(216,184,106,${intensity})`
                  : "rgba(154,174,181,0.10)"
              }
              strokeWidth={isActive ? activeStrokeW : 1}
              strokeLinecap="round"
            />
          );
        })}
        {/* Nodes */}
        {GRAPH_NODES.map((node) => {
          const label = SIGNAL_LABELS[node.id];
          const isActive = activePair.includes(node.id) && confirmed;
          return (
            <g key={node.id} className={`graph-node ${isActive ? "active" : ""}`}>
              <circle cx={node.x} cy={node.y} r={isActive ? 17 : 12} />
              {isActive && (
                <text x={node.x} y={node.y + 30} className="rel-node-label">
                  {label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="rel-map-legend">
        <span>Line weight = covariance shift · Only active pair labelled</span>
        {confirmed && <span>Shift: {fmt(covShift, 3)}</span>}
      </div>
    </section>
  );
}

// ── EngineerChartsSection ──────────────────────────────────────────────────────

function EngineerChartsSection({ history, firstConfirmedIdx }) {
  const extract = (key1, key2) =>
    history
      .map((h) => h.output.engineer?.[key1]?.[key2])
      .filter((v) => typeof v === "number");

  const driftVals = extract("structural_metrics", "drift_score");
  const covVals = extract("structural_metrics", "covariance_shift");
  const stabilityVals = extract("structural_metrics", "relational_stability");
  const velocityVals = extract("trajectory_metrics", "drift_velocity");

  const fci = firstConfirmedIdx >= 0 ? firstConfirmedIdx : null;

  return (
    <section className="v4-panel eng-charts-panel">
      <p className="label">Structural Metrics · over time</p>
      <div className="eng-charts-2x2">
        <AnnotatedChart label="Drift Score" values={driftVals} color="#ff695f" fci={fci} />
        <AnnotatedChart label="Covariance Shift" values={covVals} color="#d8b86a" fci={fci} />
        <AnnotatedChart label="Relational Stability" values={stabilityVals} color="#6e8f7d" fci={fci} />
        <AnnotatedChart label="Drift Velocity" values={velocityVals} color="#9dafb5" fci={fci} zero />
      </div>
      {fci !== null && (
        <p className="charts-confirmed-note">
          <span className="charts-confirm-mark">┊</span> dashed line = first confirmed change
        </p>
      )}
    </section>
  );
}

function AnnotatedChart({ label, values, color, fci, zero = false }) {
  const hasData = values.length >= 2;
  const min = hasData ? (zero ? Math.min(0, ...values) : Math.min(...values)) : 0;
  const max = hasData ? (zero ? Math.max(0, ...values) : Math.max(...values)) : 1;
  const range = max - min || 1;

  function toY(v) {
    return 50 - ((v - min) / range) * 46;
  }

  const pts = hasData
    ? values.map((v, i) => `${(i / (values.length - 1)) * 100},${toY(v)}`).join(" ")
    : "";

  const confirmX =
    fci !== null && hasData && fci < values.length
      ? (fci / (values.length - 1)) * 100
      : null;

  const current = values.length > 0 ? values[values.length - 1] : null;

  return (
    <div className="ann-chart-cell">
      <div className="ann-chart-head">
        <span className="ann-chart-label">{label}</span>
        <span className="ann-chart-val">{current !== null ? fmt(current, 3) : "—"}</span>
      </div>
      <svg viewBox="0 0 100 54" className="ann-chart-svg" preserveAspectRatio="none">
        {zero && hasData && (
          <line x1="0" y1={toY(0)} x2="100" y2={toY(0)} stroke="#1e2d33" strokeWidth="1" />
        )}
        {confirmX !== null && (
          <line
            x1={confirmX} y1="0" x2={confirmX} y2="54"
            stroke="rgba(216,184,106,0.55)"
            strokeWidth="1"
            strokeDasharray="3,2"
          />
        )}
        {hasData ? (
          <polyline
            points={pts}
            fill="none"
            stroke={color}
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        ) : (
          <line x1="0" y1="27" x2="100" y2="27" stroke="#1e2d33" strokeWidth="1" />
        )}
      </svg>
    </div>
  );
}

// ── DemoControlsSection ────────────────────────────────────────────────────────

function DemoControlsSection({
  demoCtrl, selectedData, selectedMachineId, onNavigate,
  apiBase, setApiBase, sourceMode, setSourceMode,
  setCsvRows, setCsvName, setCsvError, csvRows, csvName, csvError,
  onResetMachine,
}) {
  const [showSettings, setShowSettings] = useState(false);

  return (
    <section className="v4-panel demo-controls-section">
      <p className="label">Demo Controls</p>
      <div className="demo-ctrl-row">
        <div className="demo-ctrl-group">
          <span className="demo-ctrl-label">Speed</span>
          <div className="demo-speed-btns">
            {["slow", "normal", "fast"].map((s) => (
              <button
                key={s} type="button"
                className={`speed-btn ${demoCtrl.demoSpeed === s ? "active" : ""}`}
                onClick={() => demoCtrl.onSpeedChange(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        <div className="demo-ctrl-group">
          <span className="demo-ctrl-label">Machine</span>
          <div className="demo-speed-btns">
            {MACHINE_LIST.map((m) => (
              <button
                key={m.id} type="button"
                className={`speed-btn ${selectedMachineId === m.id ? "active" : ""}`}
                onClick={() => onNavigate(m.id)}
              >
                {m.id}
              </button>
            ))}
          </div>
        </div>
        <div className="demo-ctrl-group">
          <span className="demo-ctrl-label">Actions</span>
          <div className="button-row demo-action-btns">
            <button type="button" onClick={onResetMachine}>Reset Machine</button>
            <button type="button" onClick={demoCtrl.onResetAll}>Reset All</button>
            <button
              type="button" className="primary"
              onClick={demoCtrl.onStart} disabled={demoCtrl.isRunning}
            >
              Start Demo
            </button>
            <button type="button" onClick={demoCtrl.onStop} disabled={!demoCtrl.isRunning}>
              Stop
            </button>
          </div>
        </div>
      </div>

      <div className="demo-readouts">
        <Metric label="Cycle" value={selectedData?.cycle || 0} />
        <Metric label="Backend" value={demoCtrl.backendConnected ? "connected" : "disconnected"} />
        <Metric label="Last update" value={selectedData?.lastUpdate || "—"} />
        <Metric
          label="Input source"
          value={sourceMode === "csv" ? `CSV (${csvRows.length} rows)` : "Built-in demo"}
        />
      </div>

      {demoCtrl.error && <p className="error-text">{demoCtrl.error}</p>}

      <button
        type="button"
        className="demo-settings-toggle"
        onClick={() => setShowSettings((o) => !o)}
      >
        Settings {showSettings ? "▲" : "▼"}
      </button>

      {showSettings && (
        <SettingsPanel
          apiBase={apiBase} setApiBase={setApiBase}
          sourceMode={sourceMode} setSourceMode={setSourceMode}
          csvRows={csvRows} setCsvRows={setCsvRows}
          csvName={csvName} setCsvName={setCsvName}
          csvError={csvError} setCsvError={setCsvError}
        />
      )}
    </section>
  );
}

// ── IncidentPanel ──────────────────────────────────────────────────────────────

function IncidentPanel({ openEvent, status, noteInput, setNoteInput, onAcknowledge, onAddNote, onClose, onBrief }) {
  const hasEvent = !!openEvent;
  const isConfirmed = status === "ALERT" || status === "ALERT_HELD";

  return (
    <section className="v4-panel incident-panel">
      <p className="label">Incident Workflow</p>
      {!hasEvent && (
        <p className="panel-empty">
          {isConfirmed
            ? "Event record not yet loaded — refresh after demo confirms."
            : "No confirmed structural change recorded for this machine."}
        </p>
      )}
      {hasEvent && (
        <div className="incident-event-status">
          <span className="incident-event-id">{openEvent.event_id}</span>
          {openEvent.acknowledged && <span className="incident-ack-badge">Acknowledged</span>}
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
        <button type="button" className="primary" onClick={onBrief} disabled={!hasEvent}>
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
          <button type="button" onClick={onAddNote} disabled={!noteInput.trim()}>Add Note</button>
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
    </section>
  );
}

// ── BriefModal ─────────────────────────────────────────────────────────────────

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
          <button type="button" className="modal-close-btn" onClick={onClose}>×</button>
        </div>
        {data.error ? (
          <p className="error-text" style={{ padding: "16px" }}>{data.error}</p>
        ) : (
          <div className="brief-body">
            <div className="brief-section">
              <span>What changed</span>
              <p>{data.what_changed}</p>
            </div>
            <div className="brief-section">
              <span>When detected</span>
              <p>{data.when_detected ? new Date(data.when_detected).toLocaleString() : "unknown"}</p>
            </div>
            <div className="brief-section">
              <span>Current status</span>
              <p>{data.current_status}</p>
            </div>
            <div className="brief-section">
              <span>Primary CNC signals</span>
              <div className="brief-tags">
                {(data.primary_signals || []).map((s) => <strong key={s}>{s}</strong>)}
              </div>
            </div>
            <div className="brief-section">
              <span>Where to inspect</span>
              <div className="brief-tags">
                {(data.where_to_inspect || []).map((loc) => <strong key={loc}>{loc}</strong>)}
              </div>
            </div>
            <div className="brief-section">
              <span>Recommended action</span>
              <p>{data.recommended_action}</p>
            </div>
            {Object.keys(ev).length > 0 && (
              <div className="brief-section">
                <span>Engineer evidence summary</span>
                <div className="brief-evidence-grid">
                  <Metric label="Drift score" value={fmt(ev.drift_score)} />
                  <Metric label="Rel. stability" value={fmt(ev.relational_stability)} />
                  <Metric label="Direction" value={ev.direction || "—"} />
                  <Metric label="Urgency" value={ev.urgency || "—"} />
                  <Metric label="Pattern" value={ev.pattern || "none"} />
                  <Metric label="Cov. shift" value={fmt(ev.covariance_shift)} />
                </div>
              </div>
            )}
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

// ── EngineerDrawer ─────────────────────────────────────────────────────────────

function EngineerDrawer({ engineer }) {
  const metrics = engineer.structural_metrics || {};
  const evidence = engineer.evidence || {};
  const relationships = engineer.contributors?.top_relationships || [];
  const trajectory = engineer.trajectory_metrics || {};
  return (
    <div className="drawer-body">
      <div className="evidence-grid">
        <Metric label="Drift score" value={fmt(metrics.drift_score)} />
        <Metric label="Relational stability" value={fmt(metrics.relational_stability)} />
        <Metric label="Covariance shift" value={fmt(metrics.covariance_shift)} />
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
              <span>cov {fmt(rel.covariance_shift_norm)}</span>
              <span>corr {fmt(rel.correlation_shift)}</span>
              <span>current {fmt(rel.current_correlation)}</span>
              <span>baseline {fmt(rel.baseline_correlation)}</span>
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

// ── EngineeringConsole (V3 preserved) ─────────────────────────────────────────

function EngineeringConsole({
  machine, data, engineer, operator, status,
  packOpen, setPackOpen, respOpen, setRespOpen, demoCtrl, onNavigate,
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

  const extract = (k1, k2) =>
    history.map((h) => h.output.engineer?.[k1]?.[k2]).filter((v) => typeof v === "number");

  return (
    <div className="eng-console" style={{ marginTop: 0 }}>
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
                {lastSignals[name] !== undefined ? lastSignals[name].toFixed(4) : "—"}
              </strong>
            </div>
          ))}
        </div>
      </section>

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

      <div className="eng-split-row">
        <section className="eng-section eng-metrics-charts">
          <p className="label">Structural Metrics · over time</p>
          <div className="eng-metrics-grid">
            <MetricChart label="Drift Score" values={extract("structural_metrics", "drift_score")} color="#ff695f" />
            <MetricChart label="Relational Stability" values={extract("structural_metrics", "relational_stability")} color="#6e8f7d" />
            <MetricChart label="Covariance Shift" values={extract("structural_metrics", "covariance_shift")} color="#d8b86a" />
            <MetricChart label="Drift Velocity" values={extract("trajectory_metrics", "drift_velocity")} color="#9dafb5" zero />
          </div>
        </section>
        <section className="eng-section eng-families">
          <p className="label">Evidence Families</p>
          <div className="eng-family-list">
            {Object.entries({ sensor_deviation: "Sensor Deviation", relationship_shift: "Relationship Shift", relational_stability_change: "Relational Stability Change", trajectory_pressure: "Trajectory Pressure" }).map(([key, label]) => {
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
            <Metric label="Persistence satisfied" value={evidence.persistence_satisfied ? "YES" : "NO"} />
          </div>
        </section>
      </div>

      <section className="eng-section">
        <p className="label">Relationship Table</p>
        {relationships.length === 0 ? (
          <p className="eng-empty">No relationship evidence yet.</p>
        ) : (
          <div className="eng-rel-table">
            <div className="eng-rel-header">
              <span>Signal Pair</span><span>Cov Shift</span><span>Corr Shift</span>
              <span>Current Corr</span><span>Baseline Corr</span>
            </div>
            {relationships.map((rel) => (
              <div key={rel.pair.join("-")} className="eng-rel-row">
                <span className="eng-rel-pair">{rel.pair.map((id) => SIGNAL_LABELS[id] || id).join(" / ")}</span>
                <span>{fmt(rel.covariance_shift_norm)}</span>
                <span>{fmt(rel.correlation_shift)}</span>
                <span>{fmt(rel.current_correlation)}</span>
                <span>{fmt(rel.baseline_correlation)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="eng-split-row">
        <section className="eng-section">
          <button type="button" className="eng-collapsible-btn" onClick={() => setPackOpen((o) => !o)}>
            Raw Packet Inspector <span>{packOpen ? "▲" : "▼"}</span>
          </button>
          {packOpen && (
            <pre className="eng-json-view">
              {lastPacket ? JSON.stringify(lastPacket, null, 2) : "No packet sent yet."}
            </pre>
          )}
        </section>
        <section className="eng-section">
          <button type="button" className="eng-collapsible-btn" onClick={() => setRespOpen((o) => !o)}>
            Raw Response Inspector <span>{respOpen ? "▲" : "▼"}</span>
          </button>
          {respOpen && (
            <pre className="eng-json-view">
              {data?.systemOutput ? JSON.stringify(data.systemOutput, null, 2) : "No response yet."}
            </pre>
          )}
        </section>
      </div>
    </div>
  );
}

// ── SettingsPanel ──────────────────────────────────────────────────────────────

function SettingsPanel({
  apiBase, setApiBase, sourceMode, setSourceMode,
  csvRows, setCsvRows, csvName, setCsvName, csvError, setCsvError,
}) {
  async function handleCsvUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const rows = parseCsvSignals(text);
      setCsvRows(rows); setCsvName(file.name); setCsvError(""); setSourceMode("csv");
    } catch (err) {
      setCsvRows([]); setCsvName(""); setCsvError(err.message);
    }
  }
  return (
    <div className="settings-grid" style={{ marginTop: 18 }}>
      <article className="settings-panel">
        <p className="label">Backend API</p>
        <label className="field-label" htmlFor="api-base">API base URL</label>
        <input id="api-base" value={apiBase} onChange={(e) => setApiBase(e.target.value.trim())} placeholder="http://127.0.0.1:8000" />
        <p className="control-note">Use <strong>/api</strong> through the Vite proxy, or full URL for direct FastAPI access.</p>
      </article>
      <article className="settings-panel">
        <p className="label">Input Source</p>
        <div className="source-toggle">
          <button type="button" className={sourceMode === "demo" ? "active" : ""} onClick={() => setSourceMode("demo")}>Built-in demo</button>
          <button type="button" className={sourceMode === "csv" ? "active" : ""} onClick={() => setSourceMode("csv")} disabled={csvRows.length === 0}>Loaded CSV</button>
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
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

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
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${34 - ((v - min) / range) * 32}`).join(" ");
  return (
    <svg viewBox="0 0 100 36" className="mini-chart-svg" preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function MetricChart({ label, values, color = "#d8b86a", zero = false }) {
  const hasData = values.length >= 2;
  const min = hasData ? (zero ? Math.min(0, ...values) : Math.min(...values)) : 0;
  const max = hasData ? (zero ? Math.max(0, ...values) : Math.max(...values)) : 1;
  const range = max - min || 1;
  const pts = hasData
    ? values.map((v, i) => `${(i / (values.length - 1)) * 100},${44 - ((v - min) / range) * 40}`).join(" ")
    : "";
  const current = values.length > 0 ? values[values.length - 1] : null;
  return (
    <div className="metric-chart-cell">
      <div className="metric-chart-head">
        <span className="eng-chart-label">{label}</span>
        <span className="metric-chart-val">{current !== null ? fmt(current) : "—"}</span>
      </div>
      <svg viewBox="0 0 100 48" className="metric-chart-svg" preserveAspectRatio="none">
        {zero && hasData && (
          <line x1="0" y1={44 - ((0 - min) / range) * 40} x2="100" y2={44 - ((0 - min) / range) * 40} stroke="#2a3b42" strokeWidth="1" />
        )}
        {hasData ? (
          <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
        ) : (
          <line x1="0" y1="24" x2="100" y2="24" stroke="#2a3b42" strokeWidth="1" />
        )}
      </svg>
    </div>
  );
}

// ── Utilities ──────────────────────────────────────────────────────────────────

function parseCsvSignals(text) {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
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
      if (!Number.isFinite(value))
        throw new Error(`CSV row ${rowIndex + 2} has non-numeric value for ${name}.`);
      signals[name] = value;
    });
    return signals;
  });
}

function splitCsvLine(line) {
  return line.split(",").map((cell) => cell.trim().replace(/^"|"$/g, ""));
}

export default App;
