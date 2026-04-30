let socket;
let latest = null;

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

function renderAll(data) {
  latest = data;

  const rt = data.runtime || {};
  const s = data.arduino_status || {};

  const currentTime = data.current_time_label ?? "-";
  const currentInterval = data.current_interval_label ?? "-";
  const currentSlot = data.current_slot;
  const currentPrice = data.current_price;
  const mode = s.mode || "-";
  const scenario = getScenarioLabel(mode);
  const priceScheme = getPriceScheme(currentPrice);

  setText("kpiTime", currentTime);
  setText("kpiInterval", currentInterval);
  setText("kpiSlot", currentSlot ?? "-");
  setText("kpiPrice", `${fmt(currentPrice, 5)} DKK/kWh`);
  setText("kpiScheme", priceScheme);
  setText("kpiScenario", scenario);

  setText("modeText", mode);
  setText("zoneText", rt.price_zone ?? "-");
  setText("clientsText", rt.clients ?? "-");
  setText("sourceText", rt.price_source ?? "-");
  setText("sketchSlotText", s.slot ?? "-");

  setText(
    "priceReceivedText",
    s.priceReceived === 1 ? "Yes" : (s.priceReceived === 0 ? "No" : "-")
  );

  setText("lastUpdateText", `Last update: ${rt.last_price_update || "-"}`);
  setText("errorText", rt.last_error || "");
  setText("scenarioDescription", getScenarioDescription(scenario));

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

  const zoneSelect = document.getElementById("zoneSelect");
  if (zoneSelect) {
    zoneSelect.addEventListener("change", (e) => {
      sendControl("set_zone", { zone: e.target.value });
    });
  }
});