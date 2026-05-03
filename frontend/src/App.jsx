import { useEffect, useRef, useState } from "react";

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_NERAIUM_API_BASE || "/api";
const BASELINE_N = 50;

const SIGNAL_NAMES = [
  "spindle_vibration",
  "spindle_motor_current",
  "coolant_flow_rate",
  "axis_servo_load",
  "cutting_zone_temperature",
];

const SIGNAL_LABELS = {
  spindle_vibration: "Spindle Vibration",
  spindle_motor_current: "Spindle Motor Current",
  coolant_flow_rate: "Coolant Flow Rate",
  axis_servo_load: "Axis Servo Load",
  cutting_zone_temperature: "Cutting Zone Temp",
};

const MACHINES = [
  { id: "CNC-01", type: "5-axis mill" },
  { id: "CNC-02", type: "horizontal mill" },
  { id: "CNC-03", type: "lathe cell" },
  { id: "CNC-04", type: "grinding cell" },
];

const DEMO_SPEEDS = { slow: 1000, normal: 450, fast: 150 };

const EVIDENCE_KEYS = [
  { key: "sensor_deviation", label: "Sensor deviation" },
  { key: "relationship_shift", label: "Relationship shift" },
  { key: "relational_stability_change", label: "Relational stability change" },
  { key: "trajectory_pressure", label: "Trajectory pressure" },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(v, d = 3) {
  return typeof v === "number" && !isNaN(v) ? v.toFixed(d) : "—";
}

function createRng(seed = 42) {
  let s = seed >>> 0;
  return () => { s = (1664525 * s + 1013904223) >>> 0; return s / 4294967296; };
}

function normal(rng, m = 0, sd = 1) {
  const u1 = Math.max(rng(), 1e-15);
  return m + sd * Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * rng());
}

function demoPacket(machineId, cycle, rng) {
  const s = Object.fromEntries(SIGNAL_NAMES.map(n => [n, normal(rng)]));
  if (machineId === "CNC-01" && cycle >= 70) {
    const prog = (cycle - 70) / 120;
    const shared = normal(rng);
    const k = 0.35 + 1.25 * prog;
    const drift = 0.02 * (cycle - 70);
    s.spindle_vibration = k * shared + drift;
    s.spindle_motor_current = k * shared + normal(rng, 0, 0.04) + drift;
  }
  return s;
}

function actionWindow(trajectory, evidence) {
  if (!trajectory || trajectory.direction !== "diverging") return null;
  const v = trajectory.drift_velocity || 0;
  const a = trajectory.drift_acceleration || 0;
  const p = evidence?.persistence_satisfied ?? false;
  let window, confidence;
  if (v > 0.1 && a > 0.01)      { window = "0–30 cycles";   confidence = "high"; }
  else if (v > 0.05)             { window = "30–80 cycles";  confidence = "moderate"; }
  else                           { window = "80–150 cycles"; confidence = "low"; }
  const basis = `Sustained divergence${p ? " with confirmed evidence" : ""}`;
  return { window, confidence, basis };
}

function demoPhaseLabel(cycle) {
  if (cycle < BASELINE_N) return `Baseline (${cycle}/${BASELINE_N})`;
  if (cycle < 70) return "Stable";
  return `Coupling active (+${cycle - 70})`;
}

function emptyMachine() {
  return {
    out: { operator: { status: "INITIALIZING" }, engineer: { status: "INITIALIZING" } },
    cycle: 0,
    history: [],
    driftHistory: [],   // [{cycle, drift, watch, alert}]
    corrHistory: [],    // [{cycle, corr}]  — spindle pair correlation over time
    sigHistory: Object.fromEntries(SIGNAL_NAMES.map(n => [n, []])),
    lastSigs: null,
    milestones: { baselineFormed: null, firstWatch: null, firstAlert: null },
    lastStatus: "INITIALIZING",
  };
}

// ── Correlation matrix from signal history ────────────────────────────────────

function computeCorrMatrix(sigHistory, n = 30) {
  const cols = SIGNAL_NAMES.map(name => (sigHistory?.[name] || []).slice(-n));
  const minLen = Math.min(...cols.map(c => c.length));
  if (minLen < 2) return null;
  const data = cols.map(c => c.slice(-minLen));
  const means = data.map(d => d.reduce((s, v) => s + v, 0) / minLen);
  return data.map((di, i) => data.map((dj, j) => {
    if (i === j) return 1;
    let sxy = 0, sxx = 0, syy = 0;
    for (let k = 0; k < minLen; k++) {
      sxy += (di[k] - means[i]) * (dj[k] - means[j]);
      sxx += (di[k] - means[i]) ** 2;
      syy += (dj[k] - means[j]) ** 2;
    }
    return sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : 0;
  }));
}

// ── Covariance ellipse math (canvas) ─────────────────────────────────────────

function ellipseParams(pts) {
  if (pts.length < 3) return null;
  const mx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  const my = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  let sxx = 0, sxy = 0, syy = 0;
  for (const [x, y] of pts) {
    sxx += (x - mx) ** 2;
    sxy += (x - mx) * (y - my);
    syy += (y - my) ** 2;
  }
  const n = pts.length - 1;
  sxx /= n; sxy /= n; syy /= n;
  // eigenvalues of [[sxx,sxy],[sxy,syy]]
  const trace = sxx + syy;
  const det = sxx * syy - sxy * sxy;
  const disc = Math.max((trace / 2) ** 2 - det, 0);
  const l1 = trace / 2 + Math.sqrt(disc);
  const l2 = trace / 2 - Math.sqrt(disc);
  const angle = Math.atan2(l1 - sxx, sxy);
  const scale = Math.sqrt(5.991); // 95% CI chi2(2)
  return { mx, my, a: scale * Math.sqrt(Math.max(l1, 0)), b: scale * Math.sqrt(Math.max(l2, 0)), angle };
}

function drawEllipse(ctx, e, toX, toY, color) {
  if (!e || e.a < 1e-6 || e.b < 1e-6) return;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.setLineDash([4, 3]);
  ctx.beginPath();
  const steps = 80;
  for (let i = 0; i <= steps; i++) {
    const t = (2 * Math.PI * i) / steps;
    const lx = e.a * Math.cos(t);
    const ly = e.b * Math.sin(t);
    const rx = lx * Math.cos(e.angle) - ly * Math.sin(e.angle) + e.mx;
    const ry = lx * Math.sin(e.angle) + ly * Math.cos(e.angle) + e.my;
    i === 0 ? ctx.moveTo(toX(rx), toY(ry)) : ctx.lineTo(toX(rx), toY(ry));
  }
  ctx.stroke();
  ctx.restore();
}

// ── CovarianceChart ───────────────────────────────────────────────────────────

function CovarianceChart({ sigHistory, highlightPair }) {
  const canvasRef = useRef(null);
  const xs = sigHistory?.spindle_vibration || [];
  const ys = sigHistory?.spindle_motor_current || [];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    const W = rect.width, H = rect.height;

    ctx.fillStyle = "#060a1a";
    ctx.fillRect(0, 0, W, H);

    const n = Math.min(xs.length, ys.length);
    if (n < 3) {
      ctx.fillStyle = "#3a4a6a";
      ctx.font = "13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(`Collecting baseline… (${n}/${BASELINE_N})`, W / 2, H / 2);
      return;
    }

    const baseN = Math.min(BASELINE_N, Math.floor(n * 0.5));
    const basePts = Array.from({ length: baseN }, (_, i) => [xs[i], ys[i]]);
    const currPts = Array.from({ length: Math.min(20, n) }, (_, i) => [xs[n - 20 + i] ?? xs[i], ys[n - 20 + i] ?? ys[i]]);

    const allX = [...basePts, ...currPts].map(p => p[0]);
    const allY = [...basePts, ...currPts].map(p => p[1]);
    const margin = { l: 52, r: 20, t: 36, b: 44 };
    const pw = W - margin.l - margin.r;
    const ph = H - margin.t - margin.b;
    const xmin = Math.min(...allX), xmax = Math.max(...allX);
    const ymin = Math.min(...allY), ymax = Math.max(...allY);
    const xpad = (xmax - xmin) * 0.15 || 0.5;
    const ypad = (ymax - ymin) * 0.15 || 0.5;
    const toX = v => margin.l + ((v - xmin + xpad) / (xmax - xmin + 2 * xpad)) * pw;
    const toY = v => margin.t + ph - ((v - ymin + ypad) / (ymax - ymin + 2 * ypad)) * ph;

    // Grid
    ctx.strokeStyle = "#1a2540";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const x = margin.l + (i / 4) * pw;
      ctx.beginPath(); ctx.moveTo(x, margin.t); ctx.lineTo(x, margin.t + ph); ctx.stroke();
      const y = margin.t + (i / 4) * ph;
      ctx.beginPath(); ctx.moveTo(margin.l, y); ctx.lineTo(margin.l + pw, y); ctx.stroke();
    }

    // Axes
    ctx.strokeStyle = "#2a3a5a";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(margin.l, margin.t); ctx.lineTo(margin.l, margin.t + ph); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(margin.l, margin.t + ph); ctx.lineTo(margin.l + pw, margin.t + ph); ctx.stroke();

    // Ellipses
    const baseE = ellipseParams(basePts);
    const currE = ellipseParams(currPts);
    drawEllipse(ctx, baseE, toX, toY, "rgba(70,130,220,0.7)");
    drawEllipse(ctx, currE, toX, toY, "rgba(255,140,0,0.7)");

    // Baseline points
    ctx.fillStyle = "rgba(70,130,220,0.5)";
    for (const [x, y] of basePts) {
      ctx.beginPath(); ctx.arc(toX(x), toY(y), 2.5, 0, Math.PI * 2); ctx.fill();
    }

    // Current points
    ctx.fillStyle = "rgba(255,140,0,0.75)";
    for (const [x, y] of currPts) {
      ctx.beginPath(); ctx.arc(toX(x), toY(y), 3, 0, Math.PI * 2); ctx.fill();
    }

    // Labels
    ctx.fillStyle = "#6a8aaa";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Spindle Vibration", margin.l + pw / 2, H - 8);
    ctx.save();
    ctx.translate(14, margin.t + ph / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("Spindle Motor Current", 0, 0);
    ctx.restore();

    // Title
    ctx.fillStyle = "#a3c4e0";
    ctx.font = "bold 12px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("Cross-signal covariance shift", margin.l, 22);

    // Legend
    const lx = W - 130;
    ctx.fillStyle = "rgba(70,130,220,0.7)"; ctx.fillRect(lx, 10, 10, 10);
    ctx.fillStyle = "#8aadca"; ctx.font = "11px sans-serif"; ctx.fillText("Baseline", lx + 14, 19);
    ctx.fillStyle = "rgba(255,140,0,0.7)"; ctx.fillRect(lx, 26, 10, 10);
    ctx.fillStyle = "#8aadca"; ctx.fillText("Current", lx + 14, 35);
  }, [xs, ys, highlightPair]);

  return (
    <div className="chart-wrap">
      <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block" }} />
    </div>
  );
}

// ── StatusBadge ───────────────────────────────────────────────────────────────

function StatusBadge({ status, size = "md" }) {
  return <span className={`badge badge-${(status || "init").toLowerCase()} badge-${size}`}>{status || "—"}</span>;
}

// ── StructuralMetricsPanel ────────────────────────────────────────────────────

function StructuralMetricsPanel({ engineer }) {
  const sm = engineer?.structural_metrics || {};
  const rel = engineer?.contributors?.top_relationships?.[0] || {};
  const ev = engineer?.evidence || {};

  return (
    <div className="panel">
      <h3 className="panel-title">Structural Metrics</h3>
      <table className="kv-table">
        <tbody>
          <tr><td>Cov baseline</td><td>{fmt(rel.baseline_correlation, 4)}</td></tr>
          <tr><td>Cov current</td><td>{fmt(rel.current_correlation, 4)}</td></tr>
          <tr><td>ΔCov (shift norm)</td><td>{fmt(rel.covariance_shift_norm, 4)}</td></tr>
          <tr><td>Corr baseline</td><td>{fmt(rel.baseline_correlation, 3)}</td></tr>
          <tr><td>Corr current</td><td>{fmt(rel.current_correlation, 3)}</td></tr>
          <tr><td>Corr shift</td><td>{fmt(rel.correlation_shift, 3)}</td></tr>
          <tr><td>Drift score</td><td>{fmt(sm.structural_drift_score ?? sm.drift_score, 3)}</td></tr>
          <tr><td>Rel stability</td><td>{fmt(sm.relational_stability, 3)}</td></tr>
          <tr>
            <td>Persistence</td>
            <td className={ev.persistence_satisfied ? "val-ok" : "val-dim"}>
              {ev.persistence_satisfied ? "✓ satisfied" : "— pending"}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

// ── EvidenceFamiliesPanel ─────────────────────────────────────────────────────

function EvidenceFamiliesPanel({ engineer }) {
  const families = engineer?.evidence?.supporting_families || {};
  const active = engineer?.evidence?.active_families || [];

  return (
    <div className="panel">
      <h3 className="panel-title">Evidence Families</h3>
      <div className="family-list">
        {EVIDENCE_KEYS.map(({ key, label }) => {
          const on = families[key] === true;
          return (
            <div key={key} className={`family-row ${on ? "family-on" : "family-off"}`}>
              <span className="family-dot">{on ? "●" : "○"}</span>
              <span>{label}</span>
            </div>
          );
        })}
      </div>
      <div className="family-count">
        {active.length} of {EVIDENCE_KEYS.length} active
      </div>
    </div>
  );
}

// ── OperatorPanel ─────────────────────────────────────────────────────────────

function OperatorPanel({ operator, engineer, onHoverSignal }) {
  const op = operator || {};
  const traj = op.trajectory || {};
  const aw = actionWindow(traj, engineer?.evidence);
  const pe = op.plain_english || {};
  const wh = op.what_is_happening || {};

  return (
    <div className="panel operator-panel">
      <h3 className="panel-title">Operator View</h3>

      <div className="op-row">
        <span className="op-label">What is happening</span>
        <p className="op-val">{wh.summary || pe.what_this_means || "Awaiting structural change"}</p>
      </div>

      <div className="op-row">
        <span className="op-label">Where to look</span>
        <p className="op-val">{pe.where_to_start || "Inspect top reported signals"}</p>
      </div>

      <div className="op-row">
        <span className="op-label">Direction</span>
        <p className={`op-val direction-${traj.direction || "ambiguous"}`}>
          {traj.direction === "diverging" ? "Diverging — moving away from baseline"
            : traj.direction === "stabilizing" ? "Stabilizing — returning toward baseline"
            : traj.direction === "flat" ? "Flat — no meaningful change"
            : "Ambiguous — insufficient history"}
        </p>
      </div>

      <div className="op-row">
        <span className="op-label">Urgency</span>
        <p className={`op-val urgency-${traj.urgency || "low"}`}>
          {(traj.urgency || "low").toUpperCase()}
        </p>
      </div>

      <div className="op-row">
        <span className="op-label">Recommended next step</span>
        <p className="op-val">
          {op.recommended_next_step === "INSPECT_TOP_SIGNALS_AND_RELATIONSHIPS"
            ? "Inspect top signals and their relationships"
            : "Continue monitoring"}
        </p>
      </div>

      {op.why_it_matters?.meaning && (
        <div className="op-row">
          <span className="op-label">Why it matters</span>
          <p className="op-val muted">{op.why_it_matters.meaning}</p>
        </div>
      )}

      {op.if_ignored?.expected_behavior && (
        <div className="op-row">
          <span className="op-label">If ignored</span>
          <p className="op-val muted">{op.if_ignored.expected_behavior}</p>
        </div>
      )}

      {aw && (
        <div className="action-window">
          <div className="aw-header">Action Window</div>
          <div className="aw-body">
            <div className="aw-row">
              <span>Cycles</span><span className="aw-cycles">{aw.window}</span>
            </div>
            <div className="aw-row">
              <span>Confidence</span>
              <span className={`aw-conf conf-${aw.confidence}`}>{aw.confidence}</span>
            </div>
            <div className="aw-basis">{aw.basis}</div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── CorrTrendChart ────────────────────────────────────────────────────────────

function CorrTrendChart({ corrHistory, milestones }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    const W = rect.width, H = rect.height;
    ctx.fillStyle = "#060a1a";
    ctx.fillRect(0, 0, W, H);

    if (!corrHistory || corrHistory.length < 2) {
      ctx.fillStyle = "#3a4a6a";
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Awaiting correlation data…", W / 2, H / 2);
      return;
    }

    const mg = { l: 36, r: 16, t: 24, b: 28 };
    const pw = W - mg.l - mg.r, ph = H - mg.t - mg.b;
    const n = corrHistory.length;
    const toX = i => mg.l + (i / (n - 1)) * pw;
    const toY = v => mg.t + ph - ((v + 1) / 2) * ph; // maps [-1,1] → [bottom,top]

    // Grid & zero line
    ctx.strokeStyle = "#1a2540"; ctx.lineWidth = 1;
    [-1, -0.5, 0, 0.5, 1].forEach(v => {
      const y = toY(v);
      ctx.beginPath(); ctx.moveTo(mg.l, y); ctx.lineTo(mg.l + pw, y); ctx.stroke();
      ctx.fillStyle = "#2a3a5a"; ctx.font = "9px sans-serif"; ctx.textAlign = "right";
      ctx.fillText(v.toFixed(1), mg.l - 4, y + 3);
    });

    // Zero line accent
    ctx.strokeStyle = "rgba(255,255,255,0.12)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(mg.l, toY(0)); ctx.lineTo(mg.l + pw, toY(0)); ctx.stroke();

    // Baseline corr reference
    const baselineCorr = corrHistory.find(e => e.baseline != null)?.baseline;
    if (baselineCorr != null) {
      const yb = toY(baselineCorr);
      ctx.setLineDash([4, 4]); ctx.strokeStyle = "rgba(70,130,200,0.4)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(mg.l, yb); ctx.lineTo(mg.l + pw, yb); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(70,130,200,0.6)"; ctx.font = "9px sans-serif"; ctx.textAlign = "left";
      ctx.fillText("baseline", mg.l + 4, yb - 3);
    }

    // Coupling start marker
    if (milestones?.firstWatch != null) {
      const idx = corrHistory.findIndex(e => e.cycle >= milestones.firstWatch);
      if (idx >= 0) {
        const x = toX(idx);
        ctx.strokeStyle = "rgba(255,184,77,0.4)"; ctx.lineWidth = 1.5; ctx.setLineDash([]);
        ctx.beginPath(); ctx.moveTo(x, mg.t); ctx.lineTo(x, mg.t + ph); ctx.stroke();
      }
    }

    // Correlation line — color shifts from blue→orange as it rises
    for (let i = 1; i < n; i++) {
      const v = corrHistory[i].corr ?? 0;
      const frac = Math.max(0, Math.min(1, (v + 1) / 2));
      const r = Math.round(70 + (255 - 70) * frac);
      const g = Math.round(130 + (140 - 130) * frac);
      const b = Math.round(200 + (0 - 200) * frac);
      ctx.strokeStyle = `rgba(${r},${g},${b},0.9)`;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(toX(i - 1), toY(corrHistory[i - 1].corr ?? 0));
      ctx.lineTo(toX(i), toY(v));
      ctx.stroke();
    }

    // Last value label
    const last = corrHistory[n - 1].corr ?? 0;
    ctx.fillStyle = last > 0.6 ? "#ff8c00" : "#7aacec";
    ctx.font = "bold 11px sans-serif"; ctx.textAlign = "left";
    ctx.fillText(`${last >= 0 ? "+" : ""}${last.toFixed(3)}`, mg.l + pw + 4, toY(last) + 4);

    // Title
    ctx.fillStyle = "#a3c4e0"; ctx.font = "bold 11px sans-serif"; ctx.textAlign = "left";
    ctx.fillText("Spindle Vibration × Spindle Motor Current — correlation", mg.l, 16);
  }, [corrHistory, milestones]);

  return (
    <div className="corr-trend-wrap">
      <canvas ref={ref} style={{ width: "100%", height: "100%", display: "block" }} />
    </div>
  );
}

// ── PersistenceGate ───────────────────────────────────────────────────────────

function PersistenceGate({ evidenceCount, persistenceWindow = 5, minHits = 3 }) {
  const count = evidenceCount ?? 0;
  const satisfied = count >= minHits;
  return (
    <div className="persistence-gate">
      <div className="pg-label">
        Persistence gate
        <span className="pg-rule">{minHits}-of-{persistenceWindow}</span>
      </div>
      <div className="pg-slots">
        {Array.from({ length: persistenceWindow }, (_, i) => (
          <div
            key={i}
            className={`pg-slot ${i < count ? (satisfied ? "pg-hit-ok" : "pg-hit") : "pg-miss"}`}
            title={i < count ? "above alert threshold" : "below threshold"}
          />
        ))}
      </div>
      <div className={`pg-status ${satisfied ? "pg-satisfied" : "pg-pending"}`}>
        {satisfied ? "✓ Satisfied" : `${count} / ${minHits} needed`}
      </div>
    </div>
  );
}

// ── ContributionBars ──────────────────────────────────────────────────────────

function ContributionBars({ engineer }) {
  const sigs = engineer?.contributors?.top_signals || [];
  if (!sigs.length) return null;
  const max = Math.max(...sigs.map(s => s.contribution || 0), 0.001);
  return (
    <div className="panel contrib-panel">
      <h3 className="panel-title">Signal Contributions</h3>
      <div className="contrib-list">
        {sigs.map((s, i) => {
          const pct = ((s.contribution || 0) / max) * 100;
          const colors = ["#ff8c00", "#4682c8", "#4ade80"];
          return (
            <div key={i} className="contrib-row">
              <div className="contrib-name">{s.signal}</div>
              <div className="contrib-track">
                <div
                  className="contrib-fill"
                  style={{ width: `${pct}%`, background: colors[i] || "#4682c8" }}
                />
              </div>
              <div className="contrib-pct">{(s.contribution * 100).toFixed(1)}%</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── MachineStatusBar ──────────────────────────────────────────────────────────

function MachineStatusBar({ machData, selectedId, onSelect }) {
  return (
    <div className="machine-status-bar">
      {MACHINES.map(m => {
        const d = machData[m.id];
        const status = d?.lastStatus || "INITIALIZING";
        const isSelected = m.id === selectedId;
        return (
          <button
            key={m.id}
            className={`msb-cell ${isSelected ? "msb-selected" : ""} msb-${status.toLowerCase()}`}
            onClick={() => !isSelected && onSelect(m.id)}
            title={`${m.id} — ${status}`}
          >
            <span className="msb-id">{m.id}</span>
            <span className="msb-dot" />
            <span className="msb-status">{status}</span>
          </button>
        );
      })}
    </div>
  );
}

// ── Sparkline ─────────────────────────────────────────────────────────────────

function Sparkline({ values, color = "#4682c8", height = 32 }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || values.length < 2) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = height * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    const W = rect.width, H = height;
    ctx.clearRect(0, 0, W, H);
    const mn = Math.min(...values), mx = Math.max(...values);
    const range = mx - mn || 1;
    const toX = i => (i / (values.length - 1)) * W;
    const toY = v => H - ((v - mn) / range) * (H - 4) - 2;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = "round";
    ctx.beginPath();
    values.forEach((v, i) => i === 0 ? ctx.moveTo(toX(i), toY(v)) : ctx.lineTo(toX(i), toY(v)));
    ctx.stroke();
    // fill under
    ctx.lineTo(toX(values.length - 1), H);
    ctx.lineTo(toX(0), H);
    ctx.closePath();
    ctx.fillStyle = color.replace(")", ",0.12)").replace("rgb", "rgba");
    ctx.fill();
  }, [values, color, height]);
  return <canvas ref={ref} style={{ width: "100%", height, display: "block" }} />;
}

// ── DriftChart ────────────────────────────────────────────────────────────────

function DriftChart({ driftHistory, milestones }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    const W = rect.width, H = rect.height;
    ctx.fillStyle = "#060a1a";
    ctx.fillRect(0, 0, W, H);

    if (!driftHistory || driftHistory.length < 2) {
      ctx.fillStyle = "#3a4a6a";
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Collecting data…", W / 2, H / 2);
      return;
    }

    const mg = { l: 46, r: 16, t: 28, b: 32 };
    const pw = W - mg.l - mg.r, ph = H - mg.t - mg.b;
    const maxWatch = Math.max(...driftHistory.map(d => d.watch || 0));
    const maxAlert = Math.max(...driftHistory.map(d => d.alert || 0));
    const maxDrift = Math.max(...driftHistory.map(d => d.drift || 0));
    const yMax = Math.max(maxDrift, maxAlert) * 1.15 || 1;
    const n = driftHistory.length;
    const toX = i => mg.l + (i / (n - 1)) * pw;
    const toY = v => mg.t + ph - (v / yMax) * ph;

    // Grid lines
    ctx.strokeStyle = "#1a2540"; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = mg.t + (i / 4) * ph;
      ctx.beginPath(); ctx.moveTo(mg.l, y); ctx.lineTo(mg.l + pw, y); ctx.stroke();
    }

    // Threshold zones
    if (maxWatch > 0) {
      ctx.fillStyle = "rgba(255,184,77,0.06)";
      ctx.fillRect(mg.l, toY(maxAlert), pw, toY(maxWatch) - toY(maxAlert));
      ctx.fillStyle = "rgba(240,68,68,0.06)";
      ctx.fillRect(mg.l, mg.t, pw, toY(maxAlert) - mg.t);
    }

    // Watch threshold line
    if (maxWatch > 0) {
      const yw = toY(maxWatch);
      ctx.setLineDash([6, 4]); ctx.strokeStyle = "rgba(255,184,77,0.6)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(mg.l, yw); ctx.lineTo(mg.l + pw, yw); ctx.stroke();
      ctx.fillStyle = "rgba(255,184,77,0.8)"; ctx.font = "10px sans-serif"; ctx.textAlign = "right";
      ctx.fillText("WATCH", mg.l - 4, yw + 3);
    }
    // Alert threshold line
    if (maxAlert > 0) {
      const ya = toY(maxAlert);
      ctx.setLineDash([6, 4]); ctx.strokeStyle = "rgba(240,68,68,0.7)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(mg.l, ya); ctx.lineTo(mg.l + pw, ya); ctx.stroke();
      ctx.fillStyle = "rgba(240,68,68,0.8)"; ctx.textAlign = "right";
      ctx.fillText("ALERT", mg.l - 4, ya + 3);
    }
    ctx.setLineDash([]);

    // Milestone verticals
    const msCycles = [
      { cycle: milestones?.firstWatch, color: "rgba(255,184,77,0.4)", label: "W" },
      { cycle: milestones?.firstAlert, color: "rgba(240,68,68,0.5)", label: "A" },
    ];
    msCycles.forEach(({ cycle, color, label }) => {
      if (cycle == null) return;
      const idx = driftHistory.findIndex(d => d.cycle >= cycle);
      if (idx < 0) return;
      const x = toX(idx);
      ctx.strokeStyle = color; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(x, mg.t); ctx.lineTo(x, mg.t + ph); ctx.stroke();
      ctx.fillStyle = color; ctx.font = "bold 10px sans-serif"; ctx.textAlign = "center";
      ctx.fillText(label, x, mg.t - 4);
    });

    // Drift line
    ctx.strokeStyle = "#7aacec"; ctx.lineWidth = 2; ctx.lineJoin = "round";
    ctx.beginPath();
    driftHistory.forEach((d, i) => {
      const x = toX(i), y = toY(d.drift || 0);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Fill under drift line
    ctx.lineTo(toX(n - 1), mg.t + ph);
    ctx.lineTo(mg.l, mg.t + ph);
    ctx.closePath();
    ctx.fillStyle = "rgba(70,130,200,0.1)";
    ctx.fill();

    // X axis labels
    ctx.fillStyle = "#4a6a88"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
    ctx.fillText(`cycle ${driftHistory[0].cycle}`, mg.l, mg.t + ph + 18);
    ctx.fillText(`cycle ${driftHistory[n - 1].cycle}`, mg.l + pw, mg.t + ph + 18);

    // Title
    ctx.fillStyle = "#a3c4e0"; ctx.font = "bold 11px sans-serif"; ctx.textAlign = "left";
    ctx.fillText("Structural Drift Score", mg.l, 18);
  }, [driftHistory, milestones]);

  return (
    <div className="drift-chart-wrap">
      <canvas ref={ref} style={{ width: "100%", height: "100%", display: "block" }} />
    </div>
  );
}

// ── CorrelationHeatmap ────────────────────────────────────────────────────────

function CorrelationHeatmap({ sigHistory }) {
  const corr = computeCorrMatrix(sigHistory);
  const SHORT = ["SV", "SMC", "CF", "ASL", "CZT"];

  function cellColor(v) {
    if (v === null) return "#162035";
    const a = Math.abs(v);
    if (v > 0) return `rgba(70,130,200,${0.1 + 0.75 * a})`;
    return `rgba(220,80,60,${0.1 + 0.75 * a})`;
  }

  return (
    <div className="panel heatmap-panel">
      <h3 className="panel-title">Current Correlation</h3>
      <div className="heatmap-grid">
        <div className="hm-corner" />
        {SHORT.map(s => <div key={s} className="hm-label hm-col-label">{s}</div>)}
        {SIGNAL_NAMES.map((_, i) => (
          <>
            <div key={`row-${i}`} className="hm-label hm-row-label">{SHORT[i]}</div>
            {SIGNAL_NAMES.map((__, j) => {
              const v = corr ? corr[i][j] : null;
              return (
                <div
                  key={`${i}-${j}`}
                  className="hm-cell"
                  style={{ background: cellColor(v) }}
                  title={v != null ? `${SHORT[i]} × ${SHORT[j]}: ${v.toFixed(3)}` : ""}
                >
                  {i !== j && v != null ? (
                    <span className="hm-val">{v.toFixed(2)}</span>
                  ) : i === j ? (
                    <span className="hm-diag">1</span>
                  ) : null}
                </div>
              );
            })}
          </>
        ))}
      </div>
      <div className="hm-legend">
        <span className="hm-neg">neg</span>
        <div className="hm-grad" />
        <span className="hm-pos">pos</span>
      </div>
    </div>
  );
}

// ── MilestonesRow ─────────────────────────────────────────────────────────────

function MilestonesRow({ milestones }) {
  const { baselineFormed, firstWatch, firstAlert } = milestones || {};
  const items = [
    { label: "Baseline formed", cycle: baselineFormed, color: "#4682c8" },
    { label: "First Watch",     cycle: firstWatch,     color: "#ffb84d" },
    { label: "First Alert",     cycle: firstAlert,     color: "#f04444" },
  ];
  return (
    <div className="milestones-row">
      {items.map(({ label, cycle, color }) => (
        <div key={label} className="milestone-item">
          <span className="ms-dot" style={{ background: cycle != null ? color : "#2a3a5a" }} />
          <span className="ms-label">{label}</span>
          <span className="ms-cycle" style={{ color: cycle != null ? color : "#3a4a6a" }}>
            {cycle != null ? `cycle ${cycle}` : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── ConfidenceBar ─────────────────────────────────────────────────────────────

function ConfidenceBar({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 80 ? "#4ade80" : pct >= 50 ? "#ffb84d" : "#4682c8";
  return (
    <div className="conf-bar-wrap">
      <div className="conf-bar-track">
        <div className="conf-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="conf-bar-label" style={{ color }}>{pct}%</span>
    </div>
  );
}

// ── TelemetryStrip ────────────────────────────────────────────────────────────

function TelemetryStrip({ sigs, sigHistory }) {
  return (
    <div className="telemetry-strip">
      {SIGNAL_NAMES.map(name => {
        const v = sigs?.[name];
        const hist = (sigHistory?.[name] || []).slice(-40);
        return (
          <div key={name} className="telem-cell">
            <div className="telem-name">{SIGNAL_LABELS[name]}</div>
            <div className="telem-val">{v != null ? fmt(v, 3) : "—"}</div>
            {hist.length >= 2 && <Sparkline values={hist} color="#4682c8" height={28} />}
          </div>
        );
      })}
    </div>
  );
}

// ── StateTimeline ─────────────────────────────────────────────────────────────

function StateTimeline({ history }) {
  const tail = history.slice(-50);
  return (
    <div className="timeline-wrap">
      <div className="timeline-label">State History (last 50)</div>
      <div className="timeline-bar">
        {tail.map((h, i) => (
          <div
            key={i}
            className={`tl-dot tl-${(h.status || "init").toLowerCase()}`}
            title={`${h.cycle}: ${h.status}`}
          />
        ))}
        {tail.length === 0 && <span className="muted" style={{ fontSize: 11 }}>No history yet</span>}
      </div>
    </div>
  );
}

// ── EngineerDrawer ────────────────────────────────────────────────────────────

function EngineerDrawer({ engineer }) {
  const [open, setOpen] = useState(false);
  const sm = engineer?.structural_metrics || {};
  const tm = engineer?.trajectory_metrics || {};
  const ev = engineer?.evidence || {};
  const rels = engineer?.contributors?.top_relationships || [];
  const sigs = engineer?.contributors?.top_signals || [];

  return (
    <div className="eng-drawer">
      <button className="eng-toggle" onClick={() => setOpen(o => !o)}>
        {open ? "▾" : "▸"} Engineer Metrics
      </button>
      {open && (
        <div className="eng-content">
          <div className="eng-section">
            <div className="eng-section-title">Structural</div>
            <table className="kv-table">
              <tbody>
                <tr><td>Drift score</td><td>{fmt(sm.structural_drift_score ?? sm.drift_score, 4)}</td></tr>
                <tr><td>Rel stability</td><td>{fmt(sm.relational_stability, 4)}</td></tr>
                <tr><td>Cov shift</td><td>{fmt(sm.covariance_shift, 4)}</td></tr>
                <tr><td>Watch threshold</td><td>{fmt(sm.watch_threshold, 4)}</td></tr>
                <tr><td>Alert threshold</td><td>{fmt(sm.alert_threshold, 4)}</td></tr>
              </tbody>
            </table>
          </div>
          <div className="eng-section">
            <div className="eng-section-title">Trajectory</div>
            <table className="kv-table">
              <tbody>
                <tr><td>Direction</td><td>{tm.direction || "—"}</td></tr>
                <tr><td>Drift velocity</td><td>{fmt(tm.drift_velocity, 5)}</td></tr>
                <tr><td>Drift acceleration</td><td>{fmt(tm.drift_acceleration, 5)}</td></tr>
              </tbody>
            </table>
          </div>
          <div className="eng-section">
            <div className="eng-section-title">Evidence</div>
            <table className="kv-table">
              <tbody>
                <tr><td>Count</td><td>{ev.evidence_count ?? "—"}</td></tr>
                <tr><td>Time in state</td><td>{ev.time_in_state ?? "—"}</td></tr>
                <tr><td>Confidence</td><td>{fmt(ev.confidence_score, 3)}</td></tr>
                <tr><td>Active families</td><td>{(ev.active_families || []).length}</td></tr>
              </tbody>
            </table>
          </div>
          {rels.length > 0 && (
            <div className="eng-section">
              <div className="eng-section-title">Top Relationships</div>
              {rels.slice(0, 3).map((r, i) => (
                <div key={i} className="rel-row">
                  <span className="rel-pair">{(r.pair || []).join(" ↔ ")}</span>
                  <span className="rel-shift">Δ{fmt(r.correlation_shift, 3)}</span>
                </div>
              ))}
            </div>
          )}
          {sigs.length > 0 && (
            <div className="eng-section">
              <div className="eng-section-title">Top Signals</div>
              {sigs.map((s, i) => (
                <div key={i} className="rel-row">
                  <span className="rel-pair">{s.signal}</span>
                  <span className="rel-shift">{fmt(s.contribution, 3)}</span>
                </div>
              ))}
            </div>
          )}
          <div className="eng-section">
            <div className="eng-section-title">Pattern (engineer only)</div>
            <div className="pattern-type">{engineer?.pattern?.type || "—"}</div>
            <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{engineer?.pattern?.rule_triggered || ""}</div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── EventsPanel ───────────────────────────────────────────────────────────────

function EventsPanel({ machineId, events, onAck, onNote, onClose }) {
  const [noteText, setNoteText] = useState("");
  const openEvt = events.filter(e => e.status === "open").slice(-1)[0];

  return (
    <div className="panel events-panel">
      <h3 className="panel-title">Active Events</h3>
      {!openEvt ? (
        <p className="muted">No open events</p>
      ) : (
        <div className="event-card">
          <div className="event-id">{openEvt.event_id}</div>
          <div className="event-summary">{openEvt.summary}</div>
          <div className="event-meta">
            <StatusBadge status={openEvt.urgency?.toUpperCase()} size="sm" />
            <span className="muted">{openEvt.timestamp?.slice(0, 19).replace("T", " ")}</span>
          </div>
          {openEvt.notes?.length > 0 && (
            <div className="event-notes">
              {openEvt.notes.map((n, i) => (
                <div key={i} className="event-note">» {n.text}</div>
              ))}
            </div>
          )}
          <div className="event-actions">
            <input
              value={noteText}
              onChange={e => setNoteText(e.target.value)}
              placeholder="Add note…"
              className="note-input"
            />
            <button onClick={() => { onNote(noteText); setNoteText(""); }} disabled={!noteText}>
              Add Note
            </button>
            {!openEvt.acknowledged && (
              <button onClick={onAck} className="btn-ack">Acknowledge</button>
            )}
            <button onClick={onClose} className="btn-close-event">Close Event</button>
          </div>
        </div>
      )}
      {events.filter(e => e.status === "closed").length > 0 && (
        <div className="closed-events">
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
            {events.filter(e => e.status === "closed").length} closed event(s)
          </div>
        </div>
      )}
    </div>
  );
}

// ── MachineCard (floor view) ──────────────────────────────────────────────────

function MachineCard({ machine, data, onSelect }) {
  const status = data?.lastStatus || "INITIALIZING";
  return (
    <button className={`machine-card machine-card-${status.toLowerCase()}`} onClick={onSelect}>
      <div className="mc-id">{machine.id}</div>
      <div className="mc-type">{machine.type}</div>
      <StatusBadge status={status} size="sm" />
      <div className="mc-cycle muted">cycle {data?.cycle ?? 0}</div>
    </button>
  );
}

// ── DetailView ────────────────────────────────────────────────────────────────

function DetailView({ machineId, machine, data, events, onBack, onNote, onAck, onClose, machData, onSelectMachine }) {
  const [hover, setHover] = useState(null);
  const op  = data?.out?.operator || {};
  const eng = data?.out?.engineer || {};
  const status = op.status || "INITIALIZING";
  const timeInState = eng?.evidence?.time_in_state;
  const confidence  = eng?.evidence?.confidence_score;
  const evidenceCount = eng?.evidence?.evidence_count;
  const phase = machineId === "CNC-01" ? demoPhaseLabel(data?.cycle ?? 0) : null;

  function exportBrief() {
    const brief = {
      machine: machineId,
      cycle: data?.cycle,
      timestamp: new Date().toISOString(),
      operator: op,
      engineer: eng,
      milestones: data?.milestones,
    };
    const blob = new Blob([JSON.stringify(brief, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `neraium-brief-${machineId}-c${data?.cycle}.json`;
    a.click();
  }

  return (
    <div className={`detail-view ${status === "ALERT" || status === "ALERT_HELD" ? "state-alert-active" : ""}`}>
      {/* Machine status bar */}
      <MachineStatusBar machData={machData} selectedId={machineId} onSelect={onSelectMachine} />

      {/* Header */}
      <div className="detail-header">
        <button className="back-btn" onClick={onBack}>← Floor</button>
        <div className="dh-titles">
          <span className="dh-brand">Neraium</span>
          <span className="dh-sub">CNC Manufacturing Cell · {machine.type}</span>
          <span className="dh-tag">Live Structural Intelligence</span>
        </div>
        <div className="dh-right">
          <StatusBadge status={status} />
          {timeInState != null && (
            <span className="time-in-state muted">{timeInState}c in state</span>
          )}
          {phase && <span className="demo-phase">{phase}</span>}
          <div className="dh-cycle muted">Cycle {data?.cycle ?? 0}</div>
          <button className="btn-export" onClick={exportBrief} title="Download engineer brief as JSON">
            ↓ Brief
          </button>
        </div>
      </div>

      {/* Milestones */}
      <MilestonesRow milestones={data?.milestones} />

      {/* Main grid */}
      <div className="detail-grid">
        {/* Left column */}
        <div className="left-col">
          <CovarianceChart sigHistory={data?.sigHistory} highlightPair={hover} />
          <div className="metrics-row">
            <StructuralMetricsPanel engineer={eng} />
            <EvidenceFamiliesPanel engineer={eng} />
          </div>
          <CorrelationHeatmap sigHistory={data?.sigHistory} />
          <div className="note-banner">
            No individual signal threshold is required. Neraium detects structural relationship change.
          </div>
        </div>

        {/* Right column */}
        <div className="right-col">
          {confidence != null && <ConfidenceBar value={confidence} />}
          <PersistenceGate evidenceCount={evidenceCount} persistenceWindow={5} minHits={3} />
          <OperatorPanel operator={op} engineer={eng} onHoverSignal={setHover} />
          <ContributionBars engineer={eng} />
          <EventsPanel
            machineId={machineId}
            events={events}
            onAck={onAck}
            onNote={onNote}
            onClose={onClose}
          />
        </div>
      </div>

      {/* Correlation trend + drift chart side by side */}
      <div className="charts-row">
        <CorrTrendChart corrHistory={data?.corrHistory} milestones={data?.milestones} />
        <DriftChart driftHistory={data?.driftHistory} milestones={data?.milestones} />
      </div>

      {/* Telemetry + timeline */}
      <TelemetryStrip sigs={data?.lastSigs} sigHistory={data?.sigHistory} />
      <StateTimeline history={data?.history || []} />

      {/* Engineer drawer */}
      <EngineerDrawer engineer={eng} />
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [selected, setSelected]       = useState(null);
  const [machData, setMachData]       = useState(() => Object.fromEntries(MACHINES.map(m => [m.id, emptyMachine()])));
  const [machEvents, setMachEvents]   = useState(() => Object.fromEntries(MACHINES.map(m => [m.id, []])));
  const [running, setRunning]         = useState(false);
  const [speed, setSpeed]             = useState("normal");
  const [apiBase, setApiBase]         = useState(API_BASE);
  const [connected, setConnected]     = useState(false);
  const [error, setError]             = useState("");
  const [csvRows, setCsvRows]         = useState([]);
  const [csvName, setCsvName]         = useState("");
  const [srcMode, setSrcMode]         = useState("demo"); // "demo" | "csv"

  const timerRef    = useRef(null);
  const rngs        = useRef(Object.fromEntries(MACHINES.map((m, i) => [m.id, createRng(42 + i)])));
  const cycles      = useRef(Object.fromEntries(MACHINES.map(m => [m.id, 0])));
  const apiRef      = useRef(apiBase);
  const srcRef      = useRef(srcMode);
  const csvRef      = useRef(csvRows);

  useEffect(() => { apiRef.current = apiBase; }, [apiBase]);
  useEffect(() => { srcRef.current = srcMode; }, [srcMode]);
  useEffect(() => { csvRef.current = csvRows; }, [csvRows]);

  useEffect(() => {
    let alive = true;
    fetch(`${apiBase}/health`).then(() => alive && setConnected(true)).catch(() => alive && setConnected(false));
    return () => { alive = false; };
  }, [apiBase]);

  useEffect(() => () => stopDemo(), []);

  const runningRef = useRef(running);
  useEffect(() => { runningRef.current = running; }, [running]);

  // Spacebar → toggle start/stop
  useEffect(() => {
    function onKey(e) {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.code === "Space") {
        e.preventDefault();
        if (runningRef.current) stopDemo(); else startDemo();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function sendCycle() {
    const base = apiRef.current;
    const results = await Promise.all(MACHINES.map(async m => {
      const c = cycles.current[m.id];
      let sigs;
      if (m.id === "CNC-01" && srcRef.current === "csv" && csvRef.current.length > 0) {
        sigs = csvRef.current[c % csvRef.current.length];
        if (!sigs) return null;
      } else {
        sigs = demoPacket(m.id, c, rngs.current[m.id]);
      }
      const body = { asset_id: m.id, signals: sigs, cycle: c, timestamp: new Date().toISOString() };
      const res = await fetch(`${base}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`/update → ${res.status}`);
      const out = await res.json();
      cycles.current[m.id] = c + 1;
      return { id: m.id, c, out, sigs };
    }));

    const valid = results.filter(Boolean);
    if (!valid.length) { stopDemo(); return; }
    setConnected(true);

    setMachData(prev => {
      const next = { ...prev };
      valid.forEach(({ id, c, out, sigs }) => {
        const p = prev[id] || emptyMachine();
        const status = out?.operator?.status || "INITIALIZING";
        const ms = { ...p.milestones };
        if (!ms.baselineFormed && status !== "INITIALIZING") ms.baselineFormed = c;
        if (!ms.firstWatch && status === "WATCH")            ms.firstWatch = c;
        if (!ms.firstAlert && (status === "ALERT" || status === "ALERT_HELD")) ms.firstAlert = c;

        const newSigH = Object.fromEntries(SIGNAL_NAMES.map(n => [
          n, [...(p.sigHistory[n] || []), sigs[n] ?? 0].slice(-120),
        ]));

        const sm = out?.engineer?.structural_metrics || {};
        const driftEntry = {
          cycle: c,
          drift: sm.structural_drift_score ?? sm.drift_score ?? 0,
          watch: sm.watch_threshold ?? 0,
          alert: sm.alert_threshold ?? 0,
        };

        const topRel = out?.engineer?.contributors?.top_relationships?.[0] || {};
        const corrEntry = {
          cycle: c,
          corr: topRel.current_correlation ?? null,
          baseline: topRel.baseline_correlation ?? null,
        };

        next[id] = {
          out,
          cycle: c + 1,
          history: [...p.history, { cycle: c, status }].slice(-100),
          driftHistory: [...(p.driftHistory || []), driftEntry].slice(-150),
          corrHistory: [...(p.corrHistory || []), corrEntry].filter(e => e.corr != null).slice(-150),
          sigHistory: newSigH,
          lastSigs: sigs,
          milestones: ms,
          lastStatus: status,
        };
      });
      return next;
    });

    // Sync events from API
    const evRes = await fetch(`${apiRef.current}/events`).catch(() => null);
    if (evRes?.ok) {
      const evData = await evRes.json();
      setMachEvents(Object.fromEntries(MACHINES.map(m => [
        m.id, evData.filter(e => e.machine_id === m.id),
      ])));
    }
  }

  function startDemo() {
    if (running) return;
    setRunning(true);
    setError("");
    timerRef.current = setInterval(() => {
      sendCycle().catch(err => { setError(err.message); stopDemo(); });
    }, DEMO_SPEEDS[speed] || 450);
  }

  function stopDemo() {
    clearInterval(timerRef.current);
    timerRef.current = null;
    setRunning(false);
  }

  async function handleReset() {
    stopDemo();
    await fetch(`${apiBase}/reset`, { method: "POST" }).catch(() => {});
    setMachData(Object.fromEntries(MACHINES.map(m => [m.id, emptyMachine()])));
    setMachEvents(Object.fromEntries(MACHINES.map(m => [m.id, []])));
    MACHINES.forEach((m, i) => {
      cycles.current[m.id] = 0;
      rngs.current[m.id] = createRng(42 + i);
    });
    setError("");
  }

  function handleCsvUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvName(file.name);
    const reader = new FileReader();
    reader.onload = ev => {
      const lines = ev.target.result.trim().split("\n");
      const headers = lines[0].split(",").map(h => h.trim());
      const rows = lines.slice(1).map(line => {
        const vals = line.split(",");
        return Object.fromEntries(headers.map((h, i) => [h, parseFloat(vals[i])]));
      }).filter(r => Object.values(r).every(v => !isNaN(v)));
      setCsvRows(rows);
      setSrcMode("csv");
    };
    reader.readAsText(file);
  }

  // Event actions
  async function handleAck(machineId) {
    await fetch(`${apiBase}/events/${machineId}/acknowledge`, { method: "POST" }).catch(() => {});
    const res = await fetch(`${apiBase}/events`).catch(() => null);
    if (res?.ok) {
      const d = await res.json();
      setMachEvents(Object.fromEntries(MACHINES.map(m => [m.id, d.filter(e => e.machine_id === m.id)])));
    }
  }

  async function handleNote(machineId, text) {
    await fetch(`${apiBase}/events/${machineId}/note`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: text }),
    }).catch(() => {});
    const res = await fetch(`${apiBase}/events`).catch(() => null);
    if (res?.ok) {
      const d = await res.json();
      setMachEvents(Object.fromEntries(MACHINES.map(m => [m.id, d.filter(e => e.machine_id === m.id)])));
    }
  }

  async function handleClose(machineId) {
    await fetch(`${apiBase}/events/${machineId}/close`, { method: "POST" }).catch(() => {});
    const res = await fetch(`${apiBase}/events`).catch(() => null);
    if (res?.ok) {
      const d = await res.json();
      setMachEvents(Object.fromEntries(MACHINES.map(m => [m.id, d.filter(e => e.machine_id === m.id)])));
    }
  }

  const selMachine = MACHINES.find(m => m.id === selected);

  return (
    <div className="app">
      {/* Controls bar */}
      <div className="ctrl-bar">
        <div className="ctrl-left">
          <span className={`conn-dot ${connected ? "conn-ok" : "conn-off"}`} />
          <input
            className="api-input"
            value={apiBase}
            onChange={e => setApiBase(e.target.value)}
            title="API base URL"
          />
        </div>
        <div className="ctrl-center">
          {running && <span className="live-dot" title="Recording" />}
          <button onClick={startDemo} disabled={running} className="btn-start">▶ Start</button>
          <button onClick={stopDemo} disabled={!running}>■ Stop</button>
          <select value={speed} onChange={e => setSpeed(e.target.value)} disabled={running}>
            <option value="slow">Slow</option>
            <option value="normal">Normal</option>
            <option value="fast">Fast</option>
          </select>
          <label className={`src-toggle ${srcMode === "csv" ? "src-active" : ""}`}>
            <input type="radio" name="src" value="demo" checked={srcMode === "demo"} onChange={() => setSrcMode("demo")} /> Demo
          </label>
          <label className={`src-toggle ${srcMode === "csv" ? "src-active" : ""}`}>
            <input type="radio" name="src" value="csv" checked={srcMode === "csv"} onChange={() => setSrcMode("csv")} /> CSV
          </label>
          {srcMode === "csv" && (
            <label className="csv-upload-label">
              {csvName || "Upload CSV"}
              <input type="file" accept=".csv" onChange={handleCsvUpload} style={{ display: "none" }} />
            </label>
          )}
        </div>
        <div className="ctrl-right">
          <button onClick={handleReset} className="btn-reset">Reset</button>
        </div>
      </div>

      {error && <div className="error-bar">{error}</div>}

      {/* Floor or Detail */}
      {!selected ? (
        <div className="floor-view">
          <div className="floor-hdr">
            <div className="floor-brand">Neraium</div>
            <div className="floor-sub">Manufacturing Floor · Structural Intelligence</div>
          </div>
          <div className="machines-grid">
            {MACHINES.map(m => (
              <MachineCard
                key={m.id}
                machine={m}
                data={machData[m.id]}
                onSelect={() => setSelected(m.id)}
              />
            ))}
          </div>
          <div className="floor-note muted">
            Select a machine to view structural evidence
          </div>
        </div>
      ) : (
        <DetailView
          machineId={selected}
          machine={selMachine}
          data={machData[selected]}
          events={machEvents[selected] || []}
          onBack={() => setSelected(null)}
          onAck={() => handleAck(selected)}
          onNote={t => handleNote(selected, t)}
          onClose={() => handleClose(selected)}
          machData={machData}
          onSelectMachine={setSelected}
        />
      )}
    </div>
  );
}
