let socket = null;
let latest = null;

let lastValidRealBatteryDisplay = {
  soc: NaN,
  chargeMah: NaN,
  capacityMah: NaN,
  initialLookupVoltage: NaN,
  lookupSoc: NaN
};

function resetRealBatteryDisplayCache() {
  lastValidRealBatteryDisplay = {
    soc: NaN,
    chargeMah: NaN,
    capacityMah: NaN,
    initialLookupVoltage: NaN,
    lookupSoc: NaN
  };
}

const scenarioColors = {
  1: "rgba(148, 163, 184, 0.14)",
  2: "rgba(34, 197, 94, 0.14)",
  3: "rgba(14, 165, 233, 0.14)",
  4: "rgba(250, 204, 21, 0.15)",
  5: "rgba(99, 102, 241, 0.15)",
  6: "rgba(244, 63, 94, 0.15)"
};

const lineColors = {
  price: "#22c55e",
  threshold: "rgba(34,197,94,0.50)",
  demand: "rgba(255,255,255,0.50)",
  pv: "#facc15",
  load: "#ffffff",
  battery: "#ef4444",
  pem: "#3b82f6"
};

const localHistory = {
  cycle: null,
  pv_power_mW: Array(96).fill(null),
  load_power_mW: Array(96).fill(null),
  battery_power_mW: Array(96).fill(null),
  pem_power_mW: Array(96).fill(null),
  scenario: Array(96).fill(null)
};

function $(id) {
  return document.getElementById(id);
}

function fmt(value, digits = 3) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : "-";
}

function numeric(value, fallback = NaN) {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }

  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function truthyFlag(value, fallback = true) {
  if (value === undefined || value === null || value === "") return fallback;
  if (value === true || value === 1 || value === "1") return true;
  if (value === false || value === 0 || value === "0") return false;

  const text = String(value).trim().toLowerCase();

  if (["true", "yes", "ok", "initialised", "initialized"].includes(text)) return true;
  if (["false", "no", "waiting", "not_initialized", "not_initialised"].includes(text)) return false;

  return fallback;
}

function prettifyStatus(value) {
  return String(value || "-").replaceAll("_", " ");
}

function measurementMw(status, components, statusKey, rawWKey, componentKey) {
  return numeric(
    status?.[statusKey],
    numeric(
      components?.[componentKey],
      numeric(status?.[rawWKey], NaN) * 1000.0
    )
  );
}

function measurementMa(status, components, statusKey, rawAKey, componentKey) {
  return numeric(
    status?.[statusKey],
    numeric(
      components?.[componentKey],
      numeric(status?.[rawAKey], NaN) * 1000.0
    )
  );
}

function setText(id, text) {
  const el = $(id);

  if (el) {
    el.textContent = text;
  }
}

function setBadge(id, text, kind) {
  const el = $(id);
  if (!el) return;

  el.textContent = text;
  el.classList.remove("ok", "bad", "warn");

  if (kind) {
    el.classList.add(kind);
  }
}

function flashButton(button) {
  if (!button) return;

  button.classList.add("pressed");

  window.setTimeout(() => {
    button.classList.remove("pressed");
  }, 350);
}

function send(action, extra = {}) {
  if (!socket) return;

  socket.emit("price_control", { action, ...extra });
}

function scenarioNumberFromMode(mode) {
  const match = String(mode || "").match(/S([1-6])/);
  return match ? Number(match[1]) : null;
}

function scenarioLabel(value) {
  const n = Number(value);

  if (!Number.isFinite(n) || n < 1 || n > 6) {
    return "-";
  }

  return `S${n}`;
}

function currentSlot(data) {
  return Math.max(0, Math.min(95, Number(data.current_slot || 0)));
}

function getRuntime(data) {
  return data.runtime || {};
}

function getDemo(data) {
  return data.demo || {};
}

function getManual(data) {
  return data.manual || {};
}

function getScheduler(data) {
  return data.scheduler || {};
}

function getControl(data) {
  return data.control || {};
}

function getHydrogen(data) {
  return data.hydrogen || {};
}

function getStatus(data) {
  return data.arduino_status || {};
}

function getComponents(data) {
  return data.components || {};
}

function isEmsEnabled(data) {
  const runtime = getRuntime(data);
  return Boolean(data.ems_enabled || runtime.ems_enabled);
}

function getTargetScenario(data) {
  const scheduler = getScheduler(data);
  return Number(scheduler.target_scenario || data.target_scenario || 1);
}

function getActualScenario(data) {
  const status = getStatus(data);
  const parsed = scenarioNumberFromMode(status.mode);

  return Number(
    status.activeScenario ||
    status.active_scenario ||
    parsed ||
    data.actual_scenario ||
    data.scenario ||
    getTargetScenario(data)
  );
}

function getControlMode(data) {
  const control = getControl(data);
  return control.control_mode || data.control_mode || "-";
}

function clearLocalHistory(cycle = 0) {
  localHistory.cycle = cycle;
  localHistory.pv_power_mW.fill(null);
  localHistory.load_power_mW.fill(null);
  localHistory.battery_power_mW.fill(null);
  localHistory.pem_power_mW.fill(null);
  localHistory.scenario.fill(null);
}

function updateLocalHistory(data) {
  const demo = getDemo(data);
  const status = getStatus(data);
  const components = getComponents(data);
  const slot = currentSlot(data);
  const cycle = Number(demo.cycle || 0);

  if (localHistory.cycle === null || localHistory.cycle !== cycle) {
    clearLocalHistory(cycle);
  }

  localHistory.pv_power_mW[slot] = measurementMw(status, components, "PVpower_mW", "PVpower", "pv_power_mW");
  localHistory.load_power_mW[slot] = measurementMw(status, components, "Loadpower_mW", "Loadpower", "load_power_mW");
  localHistory.battery_power_mW[slot] = measurementMw(status, components, "Batterypower_mW", "Batterypower", "battery_power_mW");
  localHistory.pem_power_mW[slot] = measurementMw(status, components, "PEMpower_mW", "PEMpower", "pem_power_mW");
  localHistory.scenario[slot] = getActualScenario(data);
}

function seriesFromLiveHistory(data, primaryKey, fallbackKey, localKey) {
  const live = data.live_history || {};
  const source = live[primaryKey] || live[fallbackKey] || [];
  const local = localHistory[localKey] || [];
  const result = [];

  for (let i = 0; i < 96; i += 1) {
    const value = source[i];

    if (value !== null && value !== undefined && Number.isFinite(Number(value))) {
      result.push(Number(value));
    } else if (local[i] !== null && local[i] !== undefined && Number.isFinite(Number(local[i]))) {
      result.push(Number(local[i]));
    } else {
      result.push(NaN);
    }
  }

  return result;
}

function scenarioSeries(data) {
  const live = data.live_history || {};
  const source = live.scenario || [];
  const result = [];

  for (let i = 0; i < 96; i += 1) {
    const value = source[i];

    if (value !== null && value !== undefined && Number.isFinite(Number(value))) {
      result.push(Number(value));
    } else if (localHistory.scenario[i] !== null && localHistory.scenario[i] !== undefined) {
      result.push(Number(localHistory.scenario[i]));
    } else {
      result.push(null);
    }
  }

  return result;
}

function signedStoragePowerMw(rawPowerMw, scenario, storageType) {
  if (!Number.isFinite(rawPowerMw)) {
    return NaN;
  }

  const magnitudeMw = Math.abs(rawPowerMw);
  const scenarioNumber = Number(scenario);

  if (storageType === "battery") {
    if (scenarioNumber === 2) return magnitudeMw;
    if (scenarioNumber === 5) return -magnitudeMw;
  }

  if (storageType === "pem") {
    if (scenarioNumber === 3) return magnitudeMw;
    if (scenarioNumber === 6) return -magnitudeMw;
  }

  return rawPowerMw;
}

function to96(values, mapper) {
  const result = Array(96).fill(NaN);
  const source = values || [];

  for (let i = 0; i < Math.min(96, source.length); i += 1) {
    const value = source[i];

    if (value === null || value === undefined || value === "") {
      continue;
    }

    const mapped = mapper(Number(value), i);
    result[i] = Number.isFinite(mapped) ? mapped : NaN;
  }

  return result;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function intervalForSlot(slot) {
  const s = Number(slot);

  if (!Number.isFinite(s) || s < 0) {
    return "-";
  }

  const startHour = Math.floor(s / 4);
  const startMinute = (s % 4) * 15;

  let endHour = startHour;
  let endMinute = startMinute + 15;

  if (endMinute >= 60) {
    endMinute = 0;
    endHour = (endHour + 1) % 24;
  }

  return `${pad2(startHour)}:${pad2(startMinute)}-${pad2(endHour)}:${pad2(endMinute)}`;
}

function drawLine(ctx, values, mapX, mapY, color, width, dashed = false) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dashed ? [7, 5] : []);
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

function drawHorizontalLine(ctx, value, mapY, x0, x1, color, label) {
  if (!Number.isFinite(value)) return;

  const y = mapY(value);

  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.3;
  ctx.setLineDash([6, 5]);
  ctx.beginPath();
  ctx.moveTo(x0, y);
  ctx.lineTo(x1, y);
  ctx.stroke();

  if (label) {
    ctx.fillStyle = color;
    ctx.font = "12px system-ui, sans-serif";
    ctx.fillText(label, Math.max(x0 + 10, x1 - 160), y - 6);
  }

  ctx.restore();
}

function drawTimeline(data) {
  const canvas = $("emsTimeline");
  if (!canvas) return;

  updateLocalHistory(data);

  const slot = currentSlot(data);
  const prices = to96(data.prices || [], (v) => v);
  const demandMw = to96(data.demand_profile || [], (v) => v);

  const scenarios = scenarioSeries(data);

  const pvMw = seriesFromLiveHistory(data, "pv_power_mW", "pv_mw", "pv_power_mW");
  const loadMw = seriesFromLiveHistory(data, "load_power_mW", "load_mw", "load_power_mW");
  const batteryMw = seriesFromLiveHistory(data, "battery_power_mW", "battery_mw", "battery_power_mW")
    .map((v, i) => signedStoragePowerMw(v, scenarios[i], "battery"));
  const pemMw = seriesFromLiveHistory(data, "pem_power_mW", "pem_mw", "pem_power_mW")
    .map((v, i) => signedStoragePowerMw(v, scenarios[i], "pem"));

  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(760, Math.floor(rect.width));
  const height = 430;

  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  canvas.style.height = `${height}px`;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const pad = {
    left: 64,
    right: 86,
    top: 30,
    bottom: 48
  };

  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const allPower = [
    ...demandMw,
    ...pvMw,
    ...loadMw,
    ...batteryMw,
    ...pemMw
  ].filter(Number.isFinite);

  const maxPower = Math.max(50, ...allPower);
  const minPower = Math.min(0, ...allPower);
  const powerSpan = Math.max(1, maxPower - minPower);

  const validPrices = prices.filter(Number.isFinite);
  const threshold = Number(data.price_threshold);
  const priceScaleValues = Number.isFinite(threshold)
    ? [...validPrices, threshold]
    : validPrices;

  const minPrice = priceScaleValues.length ? Math.min(...priceScaleValues, 0) : 0;
  const maxPrice = priceScaleValues.length ? Math.max(...priceScaleValues, 1) : 1;
  const priceSpan = Math.max(0.001, maxPrice - minPrice);

  const mapX = (s) => pad.left + (s / 95) * plotW;
  const mapPowerY = (mw) => pad.top + plotH - ((mw - minPower) / powerSpan) * plotH;
  const mapPriceY = (price) => pad.top + plotH - ((price - minPrice) / priceSpan) * plotH;

  ctx.fillStyle = "rgba(255,255,255,0.035)";
  ctx.fillRect(pad.left, pad.top, plotW, plotH);

  scenarios.forEach((scenario, s) => {
    if (!Number.isFinite(Number(scenario))) return;

    const x0 = mapX(s);
    const x1 = mapX(Math.min(95, s + 1));

    ctx.fillStyle = scenarioColors[Number(scenario)] || "rgba(255,255,255,0.04)";
    ctx.fillRect(x0, pad.top, Math.max(2, x1 - x0), plotH);
  });

  ctx.font = "12px system-ui, sans-serif";
  ctx.strokeStyle = "rgba(255,255,255,0.13)";
  ctx.fillStyle = "rgba(255,255,255,0.72)";
  ctx.lineWidth = 1;

  for (let i = 0; i <= 4; i += 1) {
    const value = maxPower - (powerSpan / 4) * i;
    const y = mapPowerY(value);

    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotW, y);
    ctx.stroke();

    ctx.fillText(`${Math.round(value)} mW`, 10, y + 4);
  }

  const zeroY = mapPowerY(0);
  ctx.strokeStyle = "rgba(255,255,255,0.35)";
  ctx.beginPath();
  ctx.moveTo(pad.left, zeroY);
  ctx.lineTo(pad.left + plotW, zeroY);
  ctx.stroke();

  [0, 24, 48, 72, 95].forEach((s) => {
    const x = mapX(s);

    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.beginPath();
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, pad.top + plotH);
    ctx.stroke();

    ctx.fillStyle = "rgba(255,255,255,0.72)";
    ctx.fillText(intervalForSlot(s).slice(0, 5), x - 14, height - 20);
  });

  if (validPrices.length > 1) {
    ctx.fillStyle = lineColors.price;
    ctx.fillText(`${fmt(maxPrice, 2)} DKK/kWh`, width - 80, pad.top + 12);
    ctx.fillText(`${fmt(minPrice, 2)} DKK/kWh`, width - 80, pad.top + plotH);

    drawLine(ctx, prices, mapX, mapPriceY, lineColors.price, 1.8);

    if (Number.isFinite(threshold)) {
      drawHorizontalLine(
        ctx,
        threshold,
        mapPriceY,
        pad.left,
        pad.left + plotW,
        lineColors.threshold,
        `threshold ${fmt(threshold, 3)}`
      );
    }
  } else {
    ctx.fillStyle = lineColors.price;
    ctx.fillText("No price data", width - 100, pad.top + 12);
  }

  drawLine(ctx, demandMw, mapX, mapPowerY, lineColors.demand, 1.8, true);
  drawLine(ctx, pvMw, mapX, mapPowerY, lineColors.pv, 2.1);
  drawLine(ctx, loadMw, mapX, mapPowerY, lineColors.load, 2.4);
  drawLine(ctx, batteryMw, mapX, mapPowerY, lineColors.battery, 2.1);
  drawLine(ctx, pemMw, mapX, mapPowerY, lineColors.pem, 2.1);

  const currentX = mapX(slot);

  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(currentX, pad.top - 6);
  ctx.lineTo(currentX, pad.top + plotH + 6);
  ctx.stroke();

  ctx.fillStyle = "rgba(255,255,255,0.95)";
  ctx.fillText(`slot ${slot}`, Math.min(currentX + 6, width - 105), pad.top + 18);
  ctx.fillText(scenarioLabel(getActualScenario(data)), Math.min(currentX + 6, width - 105), pad.top + 36);
}

function liveValueAtCurrent(data, primaryKey, fallbackKey, localKey) {
  const slot = currentSlot(data);
  const values = seriesFromLiveHistory(data, primaryKey, fallbackKey, localKey);
  return values[slot];
}

function signedLiveValueAtCurrent(data, primaryKey, fallbackKey, localKey, storageType) {
  const slot = currentSlot(data);
  const value = liveValueAtCurrent(data, primaryKey, fallbackKey, localKey);
  const scenarios = scenarioSeries(data);
  const scenario = scenarios[slot] || getActualScenario(data);

  return signedStoragePowerMw(value, scenario, storageType);
}

function renderTimelineSummary(data) {
  const status = getStatus(data);
  const hydrogen = getHydrogen(data);
  const components = getComponents(data);
  const slot = currentSlot(data);

  const price = numeric(data.current_price, NaN);
  const demand = numeric(data.current_demand_mW, NaN);

  const pvMw = liveValueAtCurrent(data, "pv_power_mW", "pv_mw", "pv_power_mW");
  const loadMw = liveValueAtCurrent(data, "load_power_mW", "load_mw", "load_power_mW");
  const batteryMw = signedLiveValueAtCurrent(data, "battery_power_mW", "battery_mw", "battery_power_mW", "battery");
  const pemMw = signedLiveValueAtCurrent(data, "pem_power_mW", "pem_mw", "pem_power_mW", "pem");

  const batterySoc = numeric(
    status.virtualBatterySOC,
    numeric(components.virtual_battery_soc_percent, NaN)
  );
  const h2Soc = numeric(hydrogen.h2_usable_soc, numeric(status.h2_usable_soc, NaN));

  setText("timelineTime", data.current_time_label || "-");
  setText("timelineInterval", data.current_interval_label || "-");
  setText("plotPrice", Number.isFinite(price) ? `${fmt(price, 5)} DKK/kWh` : "-");
  setText("plotDemand", Number.isFinite(demand) ? `${fmt(demand, 1)} mW` : "-");
  setText("plotPV", Number.isFinite(pvMw) ? `${fmt(pvMw, 1)} mW` : "not logged yet");
  setText("plotLoad", Number.isFinite(loadMw) ? `${fmt(loadMw, 1)} mW` : "not logged yet");
  setText("plotBattery", Number.isFinite(batteryMw) ? `${fmt(batteryMw, 1)} mW` : "not logged yet");
  setText("plotPEM", Number.isFinite(pemMw) ? `${fmt(pemMw, 1)} mW` : "not logged yet");
  setText("plotBatterySoc", Number.isFinite(batterySoc) ? `${fmt(batterySoc, 1)} %` : "-");
  setText("plotHydrogen", Number.isFinite(h2Soc) ? `${fmt(h2Soc, 1)} %` : "-");
  setText("actualScenarioText", scenarioLabel(getActualScenario(data)));
  setText("currentSlotText", slot);
}

function renderMeasurements(status) {
  const tbody = $("measurementTable");
  if (!tbody) return;

  const components = latest?.components || {};

  const rows = [
    ["PV voltage", `${fmt(status.panelVoltage)} V`],
    ["Battery voltage", `${fmt(status.batteryVoltage)} V`],
    ["PEM voltage", `${fmt(status.pemrfcVoltage)} V`],
    ["Load voltage", `${fmt(status.loadVoltage)} V`],
    ["PV current", `${fmt(measurementMa(status, components, "PVcurrent_mA", "PVcurrent", "pv_current_mA"), 2)} mA`],
    ["Battery current", `${fmt(measurementMa(status, components, "Batcurrent_mA", "Batcurrent", "battery_current_mA"), 2)} mA`],
    ["PEM current", `${fmt(measurementMa(status, components, "PEMcurrent_mA", "PEMcurrent", "pem_current_mA"), 2)} mA`],
    ["Load current", `${fmt(measurementMa(status, components, "Loadcurrent_mA", "Loadcurrent", "load_current_mA"), 2)} mA`],
    ["PV power", `${fmt(measurementMw(status, components, "PVpower_mW", "PVpower", "pv_power_mW"), 2)} mW`],
    ["Battery power", `${fmt(measurementMw(status, components, "Batterypower_mW", "Batterypower", "battery_power_mW"), 2)} mW`],
    ["PEM power", `${fmt(measurementMw(status, components, "PEMpower_mW", "PEMpower", "pem_power_mW"), 2)} mW`],
    ["Load power", `${fmt(measurementMw(status, components, "Loadpower_mW", "Loadpower", "load_power_mW"), 2)} mW`],
    ["Load trigger", status.loadTrigger === 1 ? "HIGH" : status.loadTrigger === 0 ? "LOW" : "-"],
    ["Arduino mode", status.mode || "-"]
  ];

  tbody.innerHTML = rows
    .map(([key, value]) => `<tr><th>${key}</th><td>${value}</td></tr>`)
    .join("");
}

function renderScenarioButtons(actualScenario, targetScenario) {
  document.querySelectorAll(".scenario-btn").forEach((btn) => {
    const scenario = Number(btn.dataset.scenario);

    btn.classList.toggle(
      "active",
      scenario === Number(actualScenario) || scenario === Number(targetScenario)
    );
  });
}

function updateInputs(data) {
  const status = getStatus(data);
  const hydrogen = getHydrogen(data);
  const components = getComponents(data);

  const priceDateInput = $("priceDateInput");

  if (priceDateInput && document.activeElement !== priceDateInput) {
    priceDateInput.value = data.price_date || getRuntime(data).price_date || "";
  }

  const manualPriceInput = $("manualPriceInput");

  if (manualPriceInput && document.activeElement !== manualPriceInput) {
    const price = numeric(data.current_price, NaN);
    manualPriceInput.value = Number.isFinite(price) ? fmt(price, 5) : "";
  }

  const hydrogenInput = $("hydrogenEstimationInput");

  if (hydrogenInput && document.activeElement !== hydrogenInput) {
    const h2Soc = numeric(hydrogen.h2_usable_soc, numeric(status.h2_usable_soc, 0));
    hydrogenInput.value = fmt(h2Soc, 1);
  }

  const batteryInput = $("batterySocInput");

  if (batteryInput && document.activeElement !== batteryInput) {
    const batterySoc = numeric(
      status.virtualBatterySOC,
      numeric(components.virtual_battery_soc_percent, 50)
    );
    batteryInput.value = fmt(batterySoc, 1);
  }
}

function updateButtonStates(data) {
  const emsEnabled = isEmsEnabled(data);
  const demo = getDemo(data);

  const startEmsBtn = $("startEmsBtn");
  const stopEmsBtn = $("stopEmsBtn");
  const startDemoBtn = $("startDemoBtn");
  const stopDemoBtn = $("stopDemoBtn");
  const autoModeBtn = $("autoModeBtn");
  const manualModeBtn = $("manualModeBtn");

  if (startEmsBtn) {
    startEmsBtn.disabled = emsEnabled;
  }

  if (stopEmsBtn) {
    stopEmsBtn.disabled = !emsEnabled;
  }

  if (startDemoBtn) {
    startDemoBtn.disabled = !emsEnabled;
  }

  if (stopDemoBtn) {
    stopDemoBtn.disabled = !emsEnabled && !demo.running;
  }

  if (autoModeBtn) {
    autoModeBtn.disabled = !emsEnabled;
  }

  if (manualModeBtn) {
    manualModeBtn.disabled = !emsEnabled;
  }

  document.querySelectorAll(".scenario-btn").forEach((btn) => {
    btn.disabled = !emsEnabled;
  });
}

function realBatteryDisplayValues({
  realBatteryInitialized,
  realBatterySoc,
  realBatteryChargeMah,
  realBatteryCapacityMah,
  realBatteryInitialLookupVoltage,
  realBatteryLookupSoc
}) {
  const hasValidIntegratedValue =
    realBatteryInitialized &&
    Number.isFinite(realBatterySoc) &&
    Number.isFinite(realBatteryChargeMah) &&
    Number.isFinite(realBatteryCapacityMah);

  const hasValidLookupValue =
    Number.isFinite(realBatteryLookupSoc) &&
    realBatteryLookupSoc > 0.5 &&
    Number.isFinite(realBatteryInitialLookupVoltage) &&
    realBatteryInitialLookupVoltage > 0.1 &&
    Number.isFinite(realBatteryCapacityMah);

  const impossibleResetFrame =
    hasValidLookupValue &&
    hasValidIntegratedValue &&
    realBatterySoc <= 0.05 &&
    realBatteryChargeMah <= 0.01 &&
    realBatteryLookupSoc > 0.5;

  if (hasValidIntegratedValue && !impossibleResetFrame) {
    lastValidRealBatteryDisplay = {
      soc: realBatterySoc,
      chargeMah: realBatteryChargeMah,
      capacityMah: realBatteryCapacityMah,
      initialLookupVoltage: realBatteryInitialLookupVoltage,
      lookupSoc: realBatteryLookupSoc
    };

    return {
      initialized: true,
      soc: realBatterySoc,
      chargeMah: realBatteryChargeMah,
      capacityMah: realBatteryCapacityMah,
      initialLookupVoltage: realBatteryInitialLookupVoltage,
      lookupSoc: realBatteryLookupSoc
    };
  }

  if (
    impossibleResetFrame &&
    Number.isFinite(lastValidRealBatteryDisplay.soc) &&
    Number.isFinite(lastValidRealBatteryDisplay.chargeMah)
  ) {
    return {
      initialized: true,
      soc: lastValidRealBatteryDisplay.soc,
      chargeMah: lastValidRealBatteryDisplay.chargeMah,
      capacityMah: lastValidRealBatteryDisplay.capacityMah,
      initialLookupVoltage: Number.isFinite(realBatteryInitialLookupVoltage)
        ? realBatteryInitialLookupVoltage
        : lastValidRealBatteryDisplay.initialLookupVoltage,
      lookupSoc: Number.isFinite(realBatteryLookupSoc)
        ? realBatteryLookupSoc
        : lastValidRealBatteryDisplay.lookupSoc
    };
  }

  if (hasValidLookupValue && !realBatteryInitialized) {
    return {
      initialized: false,
      soc: NaN,
      chargeMah: NaN,
      capacityMah: realBatteryCapacityMah,
      initialLookupVoltage: realBatteryInitialLookupVoltage,
      lookupSoc: realBatteryLookupSoc
    };
  }

  return {
    initialized: realBatteryInitialized,
    soc: realBatterySoc,
    chargeMah: realBatteryChargeMah,
    capacityMah: realBatteryCapacityMah,
    initialLookupVoltage: realBatteryInitialLookupVoltage,
    lookupSoc: realBatteryLookupSoc
  };
}

function render(data) {
  latest = data;

  const runtime = getRuntime(data);
  const demo = getDemo(data);
  const manual = getManual(data);
  const scheduler = getScheduler(data);
  const hydrogen = getHydrogen(data);
  const status = getStatus(data);
  const components = getComponents(data);

  const actualScenario = getActualScenario(data);
  const targetScenario = getTargetScenario(data);
  const controlMode = getControlMode(data);
  const emsEnabled = isEmsEnabled(data);

  const rawLogRunning = Boolean(manual.raw_log_running);

  const realBatterySoc = numeric(
    status.realBatterySOC,
    numeric(components.real_battery_soc_percent, NaN)
  );

  const realBatteryChargeMah = numeric(
    status.realBatteryCharge_mAh,
    numeric(components.real_battery_charge_mAh, NaN)
  );

  const realBatteryCapacityMah = numeric(
    status.realBatteryCapacity_mAh,
    numeric(components.real_battery_capacity_mAh, NaN)
  );

  const realBatteryInitialized = truthyFlag(
    status.realBatterySOCInitialized ?? components.real_battery_soc_initialized,
    false
  );

  const realBatteryInitialLookupVoltage = numeric(
    status.realBatteryInitialLookupVoltage,
    numeric(components.real_battery_initial_lookup_voltage, NaN)
  );

  const realBatteryLookupSoc = numeric(
    status.realBatteryLookupEstimatedSOC,
    numeric(components.real_battery_lookup_soc_percent, NaN)
  );

  const virtualBatterySoc = numeric(
    status.virtualBatterySOC,
    numeric(components.virtual_battery_soc_percent, NaN)
  );

  const virtualBatteryChargeMah = numeric(
    status.virtualBatteryCharge_mAh,
    numeric(components.virtual_battery_charge_mAh, NaN)
  );

  const virtualBatteryCapacityMah = numeric(
    status.virtualBatteryCapacity_mAh,
    numeric(components.virtual_battery_capacity_mAh, NaN)
  );

  const h2Soc = numeric(hydrogen.h2_usable_soc, numeric(status.h2_usable_soc, NaN));

  setText("controlModeText", controlMode);
  setText("demoStatusText", demo.running ? "Running" : "Stopped");
  setText("scenarioText", scenarioLabel(actualScenario || targetScenario));

  setText("emsStatusText", emsEnabled ? "Started" : "Standby");
  setBadge(
    "emsBadge",
    emsEnabled ? "EMS: started" : "EMS: standby",
    emsEnabled ? "ok" : "warn"
  );

  setText("rawLogStatusText", rawLogRunning ? "Running" : "Stopped");
  setText("rawLogFileText", manual.raw_log_file || "-");
  setText("rawLogSamplesText", manual.raw_log_sample_count ?? 0);
  setText("lastRawLogUpdateText", manual.last_raw_log_update || "-");

  const toggleRawLogBtn = $("toggleRawLogBtn");

  if (toggleRawLogBtn) {
    toggleRawLogBtn.textContent = rawLogRunning ? "Stop raw log" : "Start raw log";
    toggleRawLogBtn.classList.toggle("active", rawLogRunning);
  }

  setText("decisionText", scheduler.reason || data.reason || "-");
  setText("targetScenarioText", scenarioLabel(targetScenario));
  setText("actualScenarioTableText", scenarioLabel(actualScenario));

  const scenarioWasRejected = Number(status.scenarioAccepted) === 0 || status.scenarioAccepted === false;

  setText(
    "rejectReasonText",
    scenarioWasRejected ? (status.lastRejectReason || status.lastError || "Rejected") : ""
  );

  setText("priceStateText", data.price_state || "-");
  setText("currentPriceText", `${fmt(data.current_price, 5)} DKK/kWh`);
  setText("currentDemandText", `${fmt(data.current_demand_mW, 1)} mW`);
  setText("pvAvailableText", data.pv_available ? "Yes" : "No");
  setText("logFileText", demo.log_file || scheduler.log_file || "-");
  setText("lastLogUpdateText", demo.last_log_update || scheduler.last_log_update || "-");
  setText("errorText", runtime.last_error || data.last_error || "-");

  const realBatteryDisplay = realBatteryDisplayValues({
    realBatteryInitialized,
    realBatterySoc,
    realBatteryChargeMah,
    realBatteryCapacityMah,
    realBatteryInitialLookupVoltage,
    realBatteryLookupSoc
  });

  setText("storageBatteryVoltageText", `${fmt(components.battery_voltage_V, 3)} V`);

  setText(
    "realBatteryInitialVoltageText",
    Number.isFinite(realBatteryDisplay.initialLookupVoltage) &&
    realBatteryDisplay.initialLookupVoltage > 0
      ? `${fmt(realBatteryDisplay.initialLookupVoltage, 3)} V`
      : "-"
  );

  setText(
    "realBatteryLookupSocText",
    Number.isFinite(realBatteryDisplay.lookupSoc)
      ? `${fmt(realBatteryDisplay.lookupSoc, 1)} %`
      : "-"
  );

  if (!realBatteryDisplay.initialized) {
    setText("realBatterySocText", "Waiting");
    setText(
      "realBatteryEnergyText",
      Number.isFinite(realBatteryDisplay.capacityMah)
        ? `- / ${fmt(realBatteryDisplay.capacityMah, 1)} mAh`
        : "-"
    );
  } else {
    setText(
      "realBatterySocText",
      Number.isFinite(realBatteryDisplay.soc)
        ? `${fmt(realBatteryDisplay.soc, 1)} %`
        : "-"
    );

    setText(
      "realBatteryEnergyText",
      Number.isFinite(realBatteryDisplay.chargeMah)
        ? `${fmt(realBatteryDisplay.chargeMah, 3)} mAh${
            Number.isFinite(realBatteryDisplay.capacityMah)
              ? ` / ${fmt(realBatteryDisplay.capacityMah, 1)} mAh`
              : ""
          }`
        : "-"
    );
  }

  setText("batterySocText", Number.isFinite(virtualBatterySoc) ? `${fmt(virtualBatterySoc, 1)} %` : "-");

  setText(
    "batteryCapacityText",
    Number.isFinite(virtualBatteryCapacityMah)
      ? `${fmt(virtualBatteryCapacityMah, 2)} mAh`
      : "-"
  );

  setText("batteryEnergyText", Number.isFinite(virtualBatteryChargeMah) ? `${fmt(virtualBatteryChargeMah, 3)} mAh` : "-");
  setText("batteryStateText", status.virtualBatteryChargeState || components.virtual_battery_charge_state || "-");

  setText("h2VolumeText", `${fmt(hydrogen.h2_volume_mL, 2)} mL`);
  setText("h2UsableText", `${fmt(hydrogen.h2_usable_mL, 2)} mL`);
  setText("h2SocText", Number.isFinite(h2Soc) ? `${fmt(h2Soc, 1)} %` : "-");
  setText("h2ModeText", hydrogen.h2_mode || status.h2_mode || "-");

  setBadge(
    "bridgeBadge",
    runtime.bridge_ok === true || data.bridge_ok === true
      ? "Bridge: OK"
      : runtime.bridge_ok === false || data.bridge_ok === false
        ? "Bridge: Error"
        : "Bridge: Pending",
    runtime.bridge_ok === true || data.bridge_ok === true
      ? "ok"
      : runtime.bridge_ok === false || data.bridge_ok === false
        ? "bad"
        : "warn"
  );

  updateInputs(data);
  renderTimelineSummary(data);
  drawTimeline(data);
  renderMeasurements(status);
  renderScenarioButtons(actualScenario, targetScenario);
  updateButtonStates(data);

  const autoBtn = $("autoModeBtn");
  const manualBtn = $("manualModeBtn");

  if (autoBtn) {
    autoBtn.classList.toggle("active", controlMode === "auto");
  }

  if (manualBtn) {
    manualBtn.classList.toggle("active", controlMode === "manual");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  socket = io();

  socket.on("connect", () => {
    setBadge("connectionBadge", "Connected", "ok");
    socket.emit("state_request", {});
  });

  socket.on("disconnect", () => {
    setBadge("connectionBadge", "Disconnected", "bad");
  });

  socket.on("telemetry", render);

  document.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => flashButton(button));
  });

  $("resetBtn")?.addEventListener("click", () => {
    clearLocalHistory(0);
    resetRealBatteryDisplayCache();
    send("reset_system");
  });

  $("startEmsBtn")?.addEventListener("click", () => {
    send("start_ems");
  });

  $("stopEmsBtn")?.addEventListener("click", () => {
    send("stop_ems");
  });

  $("startDemoBtn")?.addEventListener("click", () => {
    clearLocalHistory(0);
    send("start_demo");
  });

  $("stopDemoBtn")?.addEventListener("click", () => {
    send("stop_demo");
  });

  $("toggleRawLogBtn")?.addEventListener("click", () => {
    const running = Boolean(latest?.manual?.raw_log_running);
    send(running ? "stop_raw_log" : "start_raw_log");
  });

  $("autoModeBtn")?.addEventListener("click", () => {
    send("set_control_mode", { mode: "auto" });
  });

  $("manualModeBtn")?.addEventListener("click", () => {
    send("set_control_mode", { mode: "manual" });
  });

  $("applyPriceDateBtn")?.addEventListener("click", () => {
    const date = String($("priceDateInput")?.value || "");

    if (date) {
      clearLocalHistory(Number(latest?.demo?.cycle || 0));
      send("set_price_date", { date });
    }
  });

  $("applyManualPriceBtn")?.addEventListener("click", () => {
    const price = Number($("manualPriceInput")?.value);

    if (Number.isFinite(price)) {
      send("set_manual_price", { price });
    }
  });

  $("initHydrogenBtn")?.addEventListener("click", () => {
    const soc = Number($("hydrogenEstimationInput")?.value);

    if (Number.isFinite(soc)) {
      send("set_hydrogen_soc", { soc });
    }
  });

  $("applyBatteryBtn")?.addEventListener("click", () => {
    const soc = Number($("batterySocInput")?.value);

    if (Number.isFinite(soc)) {
      send("set_battery_soc", { soc });
    }
  });

  document.querySelectorAll(".scenario-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const scenario = Number(btn.dataset.scenario);
      send("set_manual_scenario", { scenario });
    });
  });

  window.addEventListener("resize", () => {
    if (latest) {
      drawTimeline(latest);
    }
  });
});