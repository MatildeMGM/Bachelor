let socket;
let latest = null;

const STEP_MINUTES = 5;
const MINOR_TICK_STEPS = 3;    // 15 min grid
const MAJOR_TICK_STEPS = 12;   // 1 hour grid
const LABEL_TICK_STEPS = 12;   // 4 hour labels

const Y_MIN_KW = 0;
const Y_MAX_KW = 2000;
const CUTOFF_KW = 200;

const SERIES_COLORS = {
  wind: "#60a5fa",
  used: "#22c55e",
  standby: "#eab308",
  e1: "#ef4444",
  e2: "#3b82f6",
  e3: "#a855f7",
  e4: "#14b8a6",
};

const viewState = {
  power: {
    windowSize: 180,   // number of points visible
    endIndex: null,    // null = follow latest
    dragging: false,
    dragStartX: 0,
    dragStartEndIndex: 0,
  }
};

function fmt(v, unit = "", digits = 1) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "-";
  return `${Number(v).toFixed(digits)}${unit}`;
}

function setBadge(id, text, kind) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.classList.remove("ok", "warn", "bad");
  if (kind) el.classList.add(kind);
}

function formatShortStepTime(step) {
  const totalMinutes = Number(step || 0) * STEP_MINUTES;
  const day = Math.floor(totalMinutes / (24 * 60)) + 1;
  const dayMinutes = totalMinutes % (24 * 60);
  const hours = Math.floor(dayMinutes / 60);
  const minutes = dayMinutes % 60;
  return `D${day} ${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function resizeCanvasToDisplaySize(canvas) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(300, Math.floor(rect.width));
  const height = Math.max(260, Math.floor(rect.height));

  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
}

function clamp(x, lo, hi) {
  return Math.max(lo, Math.min(hi, x));
}

function getVisibleHistory(history, key = "power") {
  const view = viewState[key];
  if (!history || history.length === 0) return [];

  const total = history.length;
  const windowSize = clamp(view.windowSize, 24, Math.max(24, total));
  const defaultEnd = total - 1;
  const endIndex = view.endIndex === null ? defaultEnd : clamp(view.endIndex, windowSize - 1, defaultEnd);
  const startIndex = Math.max(0, endIndex - windowSize + 1);

  return history.slice(startIndex, endIndex + 1);
}

function yLabelKW(v) {
  return `${(v / 1000).toFixed(1)} MW`;
}

function drawLineChart(canvasId, series, labels, history, options = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  resizeCanvasToDisplaySize(canvas);

  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#0b1324";
  ctx.fillRect(0, 0, width, height);

  if (!series || !series.length || !history || history.length < 2) return;

  const pad = { l: 72, r: 18, t: 34, b: 56 };
  const plotW = width - pad.l - pad.r;
  const plotH = height - pad.t - pad.b;

  const minY = Y_MIN_KW;
  const maxY = Y_MAX_KW;
  const spanY = maxY - minY;
  const n = Math.max(history.length, 2);

  const xAt = (idx) => pad.l + (plotW * idx) / Math.max(1, n - 1);
  const yAt = (v) => pad.t + plotH - ((v - minY) / spanY) * plotH;

  // Horizontal grid
  ctx.strokeStyle = "rgba(148,163,184,0.18)";
  ctx.lineWidth = 1;
  const yTicks = [0, 1000, 2000, 3000, 4200];
  yTicks.forEach((val) => {
    const y = yAt(val);
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(pad.l + plotW, y);
    ctx.stroke();
  });

  // Highlight cutoff line at 200 kW
  ctx.strokeStyle = "rgba(248,113,113,0.85)";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([6, 4]);
  const cutoffY = yAt(CUTOFF_KW);
  ctx.beginPath();
  ctx.moveTo(pad.l, cutoffY);
  ctx.lineTo(pad.l + plotW, cutoffY);
  ctx.stroke();
  ctx.setLineDash([]);

  // Vertical minor grid every 15 min
  ctx.strokeStyle = "rgba(71,85,105,0.18)";
  ctx.lineWidth = 1;
  history.forEach((row, idx) => {
    const step = Number(row.step || 0);
    if (step % MINOR_TICK_STEPS !== 0) return;
    const x = xAt(idx);
    ctx.beginPath();
    ctx.moveTo(x, pad.t);
    ctx.lineTo(x, pad.t + plotH);
    ctx.stroke();
  });

  // Vertical major grid every 1 hour
  ctx.strokeStyle = "rgba(148,163,184,0.28)";
  ctx.lineWidth = 1.1;
  history.forEach((row, idx) => {
    const step = Number(row.step || 0);
    if (step % MAJOR_TICK_STEPS !== 0) return;
    const x = xAt(idx);
    ctx.beginPath();
    ctx.moveTo(x, pad.t);
    ctx.lineTo(x, pad.t + plotH);
    ctx.stroke();
  });

  // Axes
  ctx.strokeStyle = "rgba(148,163,184,0.4)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, pad.t + plotH);
  ctx.lineTo(pad.l + plotW, pad.t + plotH);
  ctx.stroke();

  // Y labels
  ctx.fillStyle = "rgba(226,232,240,0.85)";
  ctx.font = "12px system-ui";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  yTicks.forEach((val) => {
    ctx.fillText(yLabelKW(val), pad.l - 10, yAt(val));
  });

  // Cutoff label
  ctx.fillStyle = "rgba(248,113,113,0.95)";
  ctx.textAlign = "left";
  ctx.fillText("0.2 MW cutoff", pad.l + 8, cutoffY - 10);

  // X labels every 4 hours + day starts
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillStyle = "rgba(226,232,240,0.8)";
  history.forEach((row, idx) => {
    const step = Number(row.step || 0);
    const totalMinutes = step * STEP_MINUTES;
    const dayMinutes = totalMinutes % (24 * 60);
    const isDayStart = dayMinutes === 0;
    const isLabelTick = step % LABEL_TICK_STEPS === 0;

    if (!isDayStart && !isLabelTick) return;

    const x = xAt(idx);
    const label = isDayStart
      ? `D${Math.floor(totalMinutes / (24 * 60)) + 1}`
      : formatShortStepTime(step).split(" ")[1];

    ctx.fillText(label, x, pad.t + plotH + 8);
  });

  // Plot lines
  series.forEach((s) => {
    ctx.strokeStyle = s.color;
    ctx.lineWidth = s.width || 2;
    ctx.beginPath();
    s.values.forEach((v, idx) => {
      const x = xAt(idx);
      const y = yAt(clamp(v, minY, maxY));
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });

  // Legend
  ctx.font = "12px system-ui";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";

  let legendX = pad.l;
  let legendY = 16;
  const rowWrap = Math.max(260, width - 120);

  labels.forEach((label, idx) => {
    const color = series[idx].color;
    const itemWidth = 95;

    if (legendX + itemWidth > rowWrap) {
      legendX = pad.l;
      legendY += 16;
    }

    ctx.fillStyle = color;
    ctx.fillRect(legendX, legendY - 5, 12, 3);
    ctx.fillStyle = "rgba(226,232,240,0.85)";
    ctx.fillText(label, legendX + 18, legendY - 3);
    legendX += itemWidth;
  });
}

function renderKPIs(current) {
  document.getElementById("kpiWind").textContent = fmt(current.wind_kw, " kW", 1);
  document.getElementById("kpiUsed").textContent = fmt(current.used_kw, " kW", 1);
  document.getElementById("kpiCurtail").textContent = fmt(current.curtailed_kw, " kW", 1);
  document.getElementById("kpiH2").textContent = fmt(current.h2_total_kg, " kg", 3);
  document.getElementById("kpiEff").textContent = fmt(current.system_efficiency * 100, " %", 2);
  document.getElementById("kpiStarts").textContent = `${current.nhs_total} / ${current.ncs_total}`;
}

function renderRuntime(data) {
  const runtime = data.runtime || {};
  const meta = data.meta || {};

  document.getElementById("rtClients").textContent = runtime.clients ?? "-";
  document.getElementById("rtInterval").textContent = fmt(runtime.step_interval_s, " s", 2);
  document.getElementById("rtSimStep").textContent = fmt((runtime.sim_step_seconds || 0) / 60, " min", 0);
  document.getElementById("rtBridge").textContent =
    runtime.bridge_ok === null ? "Pending" : (runtime.bridge_ok ? "OK" : "Error");
  document.getElementById("metaPoints").textContent = meta.profile_points ?? "-";
  document.getElementById("metaStandby").textContent = meta.standby_to_off_steps ?? "-";
  document.getElementById("runtimeNote").textContent =
    runtime.last_error || "Python simulation runs in the App Lab process and pushes live telemetry to both browser and MCU.";
  document.getElementById("approxNote").textContent = meta.approximation_note || "-";

  const running = !!runtime.running;
  setBadge("runBadge", running ? "Running" : "Paused", running ? "ok" : "warn");
  document.getElementById("toggleBtn").textContent = running ? "Pause" : "Resume";

  const strategySelect = document.getElementById("strategySelect");
  if (strategySelect && data.current?.strategy) {
    strategySelect.value = data.current.strategy;
  }

  const strategyLabel = document.getElementById("strategyLabel");
  if (strategyLabel) strategyLabel.textContent = data.current?.strategy || "-";

  const dispatchOrder = document.getElementById("dispatchOrder");
  if (dispatchOrder) {
    const order = data.current?.dispatch_order || [];
    dispatchOrder.textContent = order.length ? order.map(x => `E${x}`).join(" → ") : "-";
  }
}

function renderElectrolyzers(current) {
  const root = document.getElementById("elecGrid");
  if (!root) return;

  root.innerHTML = "";
  current.electrolyzers.forEach((e) => {
    const div = document.createElement("article");
    div.className = "elec-card";
    div.innerHTML = `
      <h3>Electrolyzer ${e.id}</h3>
      <div class="badge state-${e.state}">${e.state}</div>
      <div class="metric-list">
        <div>Requested power <strong>${fmt(e.requested_kw, " kW", 1)}</strong></div>
        <div>Actual power <strong>${fmt(e.actual_kw, " kW", 1)}</strong></div>
        <div>Hydrogen rate <strong>${fmt(e.h2_kgph, " kg/h", 3)}</strong></div>
        <div>Total hydrogen <strong>${fmt(e.h2_total_kg, " kg", 3)}</strong></div>
        <div>Temperature <strong>${fmt(e.temp_c, " °C", 2)}</strong></div>
        <div>Cooling water <strong>${fmt(e.cooling_kg_s, " kg/s", 3)}</strong></div>
        <div>Standby steps <strong>${e.standby_steps}</strong></div>
        <div>NHS / NCS <strong>${e.nhs} / ${e.ncs}</strong></div>
      </div>
    `;
    root.appendChild(div);
  });
}

function renderHistory(history) {
  const tbody = document.querySelector("#historyTable tbody");
  if (!tbody) return;

  tbody.innerHTML = "";
  history.slice(-20).reverse().forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${formatShortStepTime(row.step)}</td>
      <td>${fmt(row.wind_kw, "", 1)}</td>
      <td>${fmt(row.used_kw, "", 1)}</td>
      <td>${fmt(row.curtailed_kw, "", 1)}</td>
      <td>${fmt(row.h2_total_kg, "", 3)}</td>
      <td>${fmt(row.system_efficiency * 100, "%", 2)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderCharts(history) {
  const windowed = getVisibleHistory(history, "power");

  const wind = windowed.map(x => x.wind_kw);
  const used = windowed.map(x => x.used_kw);
  const standby = windowed.map(x => x.standby_kw ?? 0);

  const e1 = windowed.map(x => x.electrolyzers?.[0]?.actual_kw ?? 0);
  const e2 = windowed.map(x => x.electrolyzers?.[1]?.actual_kw ?? 0);
  const e3 = windowed.map(x => x.electrolyzers?.[2]?.actual_kw ?? 0);
  const e4 = windowed.map(x => x.electrolyzers?.[3]?.actual_kw ?? 0);

  drawLineChart(
    "powerCanvas",
    [
      { values: wind, color: SERIES_COLORS.wind, width: 2.5 },
      { values: used, color: SERIES_COLORS.used, width: 2.5 },
      { values: standby, color: SERIES_COLORS.standby, width: 1.8 },
      { values: e1, color: SERIES_COLORS.e1, width: 1.8 },
      { values: e2, color: SERIES_COLORS.e2, width: 1.8 },
      { values: e3, color: SERIES_COLORS.e3, width: 1.8 },
      { values: e4, color: SERIES_COLORS.e4, width: 1.8 },
    ],
    ["Wind", "Used", "Standby", "E1", "E2", "E3", "E4"],
    windowed
  );
}

function renderAll(data) {
  latest = data;
  renderKPIs(data.current);
  renderRuntime(data);
  renderElectrolyzers(data.current);
  renderHistory(data.history || []);
  renderCharts(data.history || []);
}

function sendControl(action, extra = {}) {
  if (!socket) return;
  socket.emit("sim_control", { action, ...extra });
}

function attachPowerChartInteractions() {
  const canvas = document.getElementById("powerCanvas");
  if (!canvas) return;

  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    if (!latest?.history?.length) return;

    const view = viewState.power;
    const total = latest.history.length;

    if (e.deltaY < 0) {
      view.windowSize = Math.max(24, Math.floor(view.windowSize * 0.85));
    } else {
      view.windowSize = Math.min(total, Math.floor(view.windowSize * 1.18));
    }

    if (view.endIndex !== null) {
      view.endIndex = clamp(view.endIndex, view.windowSize - 1, total - 1);
    }

    renderAll(latest);
  }, { passive: false });

  canvas.addEventListener("mousedown", (e) => {
    const view = viewState.power;
    view.dragging = true;
    view.dragStartX = e.clientX;
    view.dragStartEndIndex = view.endIndex ?? ((latest?.history?.length || 1) - 1);
  });

  window.addEventListener("mouseup", () => {
    viewState.power.dragging = false;
  });

  window.addEventListener("mousemove", (e) => {
    const view = viewState.power;
    if (!view.dragging || !latest?.history?.length) return;

    const canvasRect = canvas.getBoundingClientRect();
    const plotWidth = Math.max(100, canvasRect.width - 90);
    const dx = e.clientX - view.dragStartX;
    const pointsPerPixel = view.windowSize / plotWidth;
    const deltaPoints = Math.round(dx * pointsPerPixel);

    const total = latest.history.length;
    view.endIndex = clamp(
      view.dragStartEndIndex - deltaPoints,
      view.windowSize - 1,
      total - 1
    );

    renderAll(latest);
  });

  canvas.addEventListener("dblclick", () => {
    const view = viewState.power;
    view.endIndex = null;
    view.windowSize = 180;
    if (latest) renderAll(latest);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  socket = io(`http://${window.location.host}`);

  socket.on("connect", () => {
    setBadge("connBadge", "Connected", "ok");
    socket.emit("state_request", {});
  });

  socket.on("disconnect", () => {
    setBadge("connBadge", "Disconnected", "bad");
  });

  socket.on("telemetry", (data) => {
    latest = data;
    if (viewState.power.endIndex === null) {
      viewState.power.endIndex = null;
    }
    renderAll(data);
  });

  document.getElementById("toggleBtn").addEventListener("click", () => sendControl("toggle"));
  document.getElementById("stepBtn").addEventListener("click", () => sendControl("step"));
  document.getElementById("resetBtn").addEventListener("click", () => {
    viewState.power.endIndex = null;
    sendControl("reset");
  });

  document.getElementById("speedSelect").addEventListener("change", (e) => {
    sendControl("set_speed", { seconds: Number(e.target.value) });
  });

  const strategySelect = document.getElementById("strategySelect");
  if (strategySelect) {
    strategySelect.addEventListener("change", (e) => {
      sendControl("set_strategy", { strategy: e.target.value });
    });
  }

  attachPowerChartInteractions();

  window.addEventListener("resize", () => {
    if (latest) renderAll(latest);
  });
});