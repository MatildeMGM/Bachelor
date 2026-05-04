let socket;
let latest = null;
const plotState = {
  cycle: null,
  pointsBySlot: new Map()
};

const scenarioColors = {
  1: "rgba(150, 163, 184, 0.13)",
  2: "rgba(43, 228, 167, 0.15)",
  3: "rgba(102, 217, 255, 0.15)",
  4: "rgba(255, 204, 102, 0.17)",
  5: "rgba(122, 167, 255, 0.16)",
  6: "rgba(255, 90, 122, 0.16)"
};

function fmt(value, digits = 3) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : String(value);
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value;
}

function setBadge(id, text, kind) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.classList.remove("ok", "warn", "bad");
  if (kind) el.classList.add(kind);
}

function getPriceScheme(price) {
  const p = Number(price);
  if (!Number.isFinite(p)) return "Unknown";
  return p >= 0.6 ? "High price scheme" : "Low price scheme";
}

function getScenarioLabel(mode) {
  if (!mode) return "Unknown";

  if (mode.includes("S1")) return "Scenario 1";
  if (mode.includes("S2")) return "Scenario 2";
  if (mode.includes("S3")) return "Scenario 3";
  if (mode.includes("S4")) return "Scenario 4";
  if (mode.includes("S5")) return "Scenario 5";
  if (mode.includes("S6")) return "Scenario 6";

  return "Unknown";
}

function getScenarioNumber(mode) {
  const label = getScenarioLabel(mode);
  const match = label.match(/Scenario (\d)/);
  return match ? Number(match[1]) : 0;
}

function getScenarioDescription(scenario) {
  const descriptions = {
    "Scenario 1": "Load receives power from the grid. PV, battery and PEM RFC are off.",
    "Scenario 2": "Load receives power from the grid while PV charges the battery.",
    "Scenario 3": "Load receives power from the grid while PV charges the PEM RFC.",
    "Scenario 4": "Load receives power from PV only. Battery and PEM RFC are off.",
    "Scenario 5": "Load receives power from the battery. PV and PEM RFC are off.",
    "Scenario 6": "Load receives power from PEM RFC. Battery and PV are off.",
    "Unknown": "Scenario could not be identified from the current mode string."
  };

  return descriptions[scenario] || descriptions["Unknown"];
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatSlotInterval(slot) {
  const s = Number(slot);
  if (!Number.isFinite(s) || s < 0) return "-";

  const startHour = Math.floor(s / 4);
  const startMinute = (s % 4) * 15;

  let endHour = startHour;
  let endMinute = startMinute + 15;

  if (endMinute >= 60) {
    endMinute = 0;
    endHour = (endHour + 1) % 24;
  }

  const start = `${pad2(startHour)}:${pad2(startMinute)}`;
  const end = `${pad2(endHour)}:${pad2(endMinute)}`;
  return `${start}-${end}`;

  return `${pad2(startHour)}:${pad2(startMinute)}–${pad2(endHour)}:${pad2(endMinute)}`;
}

function renderPrices(prices, currentSlot) {
  const tbody = document.querySelector("#priceTable tbody");
  if (!tbody) return;

  tbody.innerHTML = "";

  (prices || []).forEach((price, slot) => {
    const tr = document.createElement("tr");

    let status = "";
    if (slot === Number(currentSlot)) {
      status = "Current interval";
      tr.classList.add("current-row");
    }

    tr.innerHTML = `
      <td>${slot}</td>
      <td>${formatSlotInterval(slot)}</td>
      <td>${fmt(price, 5)}</td>
      <td>${status}</td>
    `;

    tbody.appendChild(tr);
  });
}

function rememberPlotPoint(data) {
  const demo = data.demo || {};
  const scheduler = data.scheduler || {};
  const decision = scheduler.current_decision || {};
  const s = data.arduino_status || {};
  const slot = Number(data.current_slot);

  if (!Number.isFinite(slot)) return;

  if (plotState.cycle !== demo.cycle) {
    plotState.cycle = demo.cycle;
    plotState.pointsBySlot.clear();
  }

  plotState.pointsBySlot.set(slot, {
    slot,
    demandW: Number(data.current_demand_w || decision.demand_w || 0),
    loadW: Number(s.Loadpower || 0),
    pvW: Number(decision.live_pv_w || s.PVpower || 0),
    price: Number(data.current_price || 0),
    scenario: Number(getScenarioNumber(s.mode) || scheduler.target_scenario),
    reason: decision.reason || ""
  });
}

function slotToHourLabel(slot) {
  const hour = Math.floor(slot / 4);
  return `${pad2(hour)}:00`;
}

function drawLine(ctx, values, mapX, mapY, color, width, dashed = false) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dashed ? [6, 5] : []);
  ctx.beginPath();

  let started = false;
  values.forEach((value, slot) => {
    if (!Number.isFinite(value)) return;

    const x = mapX(slot);
    const y = mapY(value);

    if (!started) {
      ctx.moveTo(x, y);
      started = true;
    } else {
      ctx.lineTo(x, y);
    }
  });

  ctx.stroke();
  ctx.restore();
}

function drawTimeline(data) {
  const canvas = document.getElementById("emsTimeline");
  if (!canvas) return;

  rememberPlotPoint(data);

  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(640, Math.floor(rect.width));
  const height = 360;

  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  canvas.style.height = `${height}px`;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const pad = { left: 54, right: 58, top: 24, bottom: 42 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const prices = (data.prices || []).map(Number);
  const demand = (data.demand_profile || []).map((v) => Number(v) * 1000);
  const history = Array.from(plotState.pointsBySlot.values());
  const currentSlot = Number(data.current_slot || 0);

  const livePowerMw = history.flatMap((p) => [
    Number(p.loadW) * 1000,
    Number(p.pvW) * 1000,
    Number(p.demandW) * 1000
  ]);
  const maxMw = Math.max(160, ...demand, ...livePowerMw.filter(Number.isFinite));
  const validPrices = prices.filter(Number.isFinite);
  const minPrice = Math.min(...validPrices, 0);
  const maxPrice = Math.max(...validPrices, 1);
  const priceSpan = Math.max(0.001, maxPrice - minPrice);

  const mapX = (slot) => pad.left + (slot / 95) * plotW;
  const mapPowerY = (mw) => pad.top + plotH - (mw / maxMw) * plotH;
  const mapPriceY = (price) =>
    pad.top + plotH - ((price - minPrice) / priceSpan) * plotH;

  ctx.fillStyle = "rgba(255,255,255,0.03)";
  ctx.fillRect(pad.left, pad.top, plotW, plotH);

  history.forEach((point) => {
    const x0 = mapX(point.slot);
    const x1 = mapX(Math.min(95, point.slot + 1));
    ctx.fillStyle = scenarioColors[point.scenario] || "rgba(255,255,255,0.05)";
    ctx.fillRect(x0, pad.top, Math.max(2, x1 - x0), plotH);
  });

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 1;
  ctx.font = "12px system-ui, sans-serif";
  ctx.fillStyle = "rgba(255,255,255,0.68)";

  for (let i = 0; i <= 4; i += 1) {
    const y = pad.top + (plotH / 4) * i;
    const mw = maxMw - (maxMw / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotW, y);
    ctx.stroke();
    ctx.fillText(`${Math.round(mw)} mW`, 10, y + 4);
  }

  [0, 24, 48, 72, 95].forEach((slot) => {
    const x = mapX(slot);
    ctx.beginPath();
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, pad.top + plotH);
    ctx.stroke();
    ctx.fillText(slotToHourLabel(slot), x - 16, height - 16);
  });

  ctx.fillStyle = "rgba(122,167,255,0.78)";
  ctx.fillText(`${fmt(maxPrice, 2)} DKK/kWh`, width - 54, pad.top + 12);
  ctx.fillText(`${fmt(minPrice, 2)}`, width - 54, pad.top + plotH);

  drawLine(ctx, demand, mapX, mapPowerY, "#ffcc66", 2, true);
  drawLine(ctx, prices, mapX, mapPriceY, "#7aa7ff", 1.8);

  const loadValues = Array(96).fill(NaN);
  const pvValues = Array(96).fill(NaN);
  history.forEach((point) => {
    loadValues[point.slot] = point.loadW * 1000;
    pvValues[point.slot] = point.pvW * 1000;
  });

  drawLine(ctx, loadValues, mapX, mapPowerY, "#ffffff", 2.4);
  drawLine(ctx, pvValues, mapX, mapPowerY, "#2be4a7", 2.4);

  const currentX = mapX(currentSlot);
  ctx.strokeStyle = "rgba(255,255,255,0.65)";
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.moveTo(currentX, pad.top - 6);
  ctx.lineTo(currentX, pad.top + plotH + 6);
  ctx.stroke();

  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.fillText(`slot ${currentSlot}`, Math.min(currentX + 6, width - 96), pad.top + 16);
}

function renderAll(data) {
  latest = data;

  const rt = data.runtime || {};
  const demo = data.demo || {};
  const scheduler = data.scheduler || {};
  const decision = scheduler.current_decision || {};
  const s = data.arduino_status || {};

  const currentTime = data.current_time_label ?? "-";
  const currentInterval = data.current_interval_label ?? "-";
  const currentSlot = data.current_slot;
  const currentPrice = data.current_price;
  const mode = s.mode || "-";
  const scenario = getScenarioLabel(mode);
  const priceScheme = decision.price_state
    ? `${decision.price_state.charAt(0).toUpperCase()}${decision.price_state.slice(1)} price`
    : getPriceScheme(currentPrice);

  setText("kpiTime", currentTime);
  setText("kpiInterval", currentInterval);
  setText("kpiSlot", currentSlot ?? "-");
  setText("kpiDemand", `${fmt((data.current_demand_w || 0) * 1000, 1)} mW`);
  setText("kpiPrice", `${fmt(currentPrice, 5)} DKK/kWh`);
  setText("kpiScheme", priceScheme);
  setText("kpiScenario", scenario);

  setText("modeText", mode);
  setText("zoneText", rt.price_zone ?? "-");
  setText("clientsText", rt.clients ?? "-");
  setText("sourceText", rt.price_source ?? "-");
  setText("sketchSlotText", s.slot ?? "-");
  setText("demoCycleText", demo.cycle ?? "-");
  setText("targetScenarioText", scheduler.target_scenario ? `S${scheduler.target_scenario}` : "-");
  setText(
    "scenarioAcceptedText",
    s.scenarioAccepted === 1 ? "Yes" : (s.scenarioAccepted === 0 ? "No" : "-")
  );
  setText("rejectReasonText", s.lastRejectReason || "-");

  setText(
    "priceReceivedText",
    s.priceReceived === 1 ? "Yes" : (s.priceReceived === 0 ? "No" : "-")
  );

  setText("lastUpdateText", `Last update: ${rt.last_price_update || "-"}`);
  setText("logFileText", `Log file: ${scheduler.log_file || "-"}`);
  setText("errorText", rt.last_error || "");
  setText("scenarioDescription", getScenarioDescription(scenario));
  setText("schedulerReasonText", decision.reason || "");
  setText("plotDecision", decision.scenario_label || (scheduler.target_scenario ? `S${scheduler.target_scenario}` : "-"));
  setText("plotReason", decision.reason || "-");
  setText("plotReserve", decision.battery_reserve_soc_percent !== undefined ? `${fmt(decision.battery_reserve_soc_percent, 1)} %` : "-");
  setText("plotPV", decision.live_pv_w !== undefined ? `${fmt(decision.live_pv_w * 1000, 1)} mW` : "-");
  setText("plotActual", getScenarioNumber(s.mode) ? `S${getScenarioNumber(s.mode)}` : "-");
  setText("plotAccepted", s.scenarioAccepted === 1 ? "Yes" : (s.scenarioAccepted === 0 ? "No" : "-"));

  setText("panelVoltage", fmt(s.panelVoltage));
  setText("batteryVoltage", fmt(s.batteryVoltage));
  setText("pemrfcVoltage", fmt(s.pemrfcVoltage));
  setText("loadVoltage", fmt(s.loadVoltage));

  setText("PVcurrent", fmt(s.PVcurrent));
  setText("Batcurrent", fmt(s.Batcurrent));
  setText("PEMcurrent", fmt(s.PEMcurrent));
  setText("Loadcurrent", fmt(s.Loadcurrent));

  setText("PVpower", fmt(s.PVpower));
  setText("Batterypower", fmt(s.Batterypower));
  setText("PEMpower", fmt(s.PEMpower));
  setText("Loadpower", fmt(s.Loadpower));

  setText("batterySOC", `${fmt(s.batterySOC, 1)} %`);
  setText("batteryEnergyWh", `${fmt(s.batteryEnergyWh, 3)} Wh`);
  setText("batteryChargeState", s.batteryChargeState || "-");

  setBadge(
    "bridgeBadge",
    rt.bridge_ok === true ? "Bridge: OK" : rt.bridge_ok === false ? "Bridge: Error" : "Bridge: Pending",
    rt.bridge_ok === true ? "ok" : rt.bridge_ok === false ? "bad" : "warn"
  );

  renderPrices(data.prices || [], currentSlot);
  drawTimeline(data);

  const zoneSelect = document.getElementById("zoneSelect");
  if (zoneSelect && rt.price_zone) {
    zoneSelect.value = rt.price_zone;
  }
}

function sendControl(action, extra = {}) {
  if (!socket) return;
  socket.emit("price_control", { action, ...extra });
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
    renderAll(data);
  });

  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      sendControl("refresh");
    });
  }

  const restartDemoBtn = document.getElementById("restartDemoBtn");
  if (restartDemoBtn) {
    restartDemoBtn.addEventListener("click", () => {
      plotState.pointsBySlot.clear();
      sendControl("restart_demo");
    });
  }

  const zoneSelect = document.getElementById("zoneSelect");
  if (zoneSelect) {
    zoneSelect.addEventListener("change", (e) => {
      sendControl("set_zone", { zone: e.target.value });
    });
  }

  window.addEventListener("resize", () => {
    if (latest) drawTimeline(latest);
  });
});
