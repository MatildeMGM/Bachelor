let socket;

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

function renderInaTable(s) {
  const tbody = document.querySelector("#inaTable tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const sensors = [
    { label: "INA226_1", addr: "0x40", base: "ina1" },
    { label: "INA226_2", addr: "0x41", base: "ina2" },
    { label: "INA226_3", addr: "0x44", base: "ina3" },
    { label: "INA226_4", addr: "0x45", base: "ina4" },
  ];

  sensors.forEach(sensor => {
    const ok = Number(s[`${sensor.base}Init`]) === 1;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${sensor.label}</td>
      <td>${sensor.addr}</td>
      <td>${fmt(s[`${sensor.base}BusV`], 4)}</td>
      <td>${fmt(s[`${sensor.base}CurrentmA`], 4)}</td>
      <td>${fmt(s[`${sensor.base}PowermW`], 4)}</td>
      <td>${fmt(s[`${sensor.base}ShuntmV`], 4)}</td>
      <td>${ok ? "OK" : "FAILED"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderAll(data) {
  const rt = data.runtime || {};
  const s = data.arduino_status || {};

  setText("kpiLedMode", s.ledMode || "-");
  setText("kpiActiveLine", s.activeSignalName || "-");
  setText("kpiActivePin", s.activeSignalPin ?? "-");
  setText("kpiUpdateTime", rt.last_update || "-");

  setText("ledModeText", s.ledMode || "-");
  setText("activeSignalIndex", s.activeSignalIndex ?? "-");
  setText("activeSignalName", s.activeSignalName || "-");
  setText("activeSignalPin", s.activeSignalPin ?? "-");
  setText("lastUpdateText", `Last update: ${rt.last_update || "-"}`);
  setText("errorText", rt.last_error || "");

  setText("sensorCount", s.sensorCount ?? 4);
  setText("readInterval", s.readIntervalMs ?? "-");
  setText("totalPower", fmt(s.totalPowermW, 3));
  setText("maxCurrent", fmt(s.maxCurrentmA, 3));

  setBadge(
    "bridgeBadge",
    rt.bridge_ok === true ? "Bridge: OK" : rt.bridge_ok === false ? "Bridge: Error" : "Bridge: Pending",
    rt.bridge_ok === true ? "ok" : rt.bridge_ok === false ? "bad" : "warn"
  );

  renderInaTable(s);
}

function sendControl(action, extra = {}) {
  if (!socket) return;
  socket.emit("led_control", { action, ...extra });
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

  document.getElementById("refreshBtn").addEventListener("click", () => {
    sendControl("refresh");
  });

  document.getElementById("autoBtn").addEventListener("click", () => {
    sendControl("set_mode", { mode: "AUTO" });
  });

  document.getElementById("manualBtn").addEventListener("click", () => {
    sendControl("set_mode", { mode: "MANUAL" });
  });

  document.getElementById("intervalSelect").addEventListener("change", (e) => {
    sendControl("set_interval", { interval_ms: Number(e.target.value) });
  });

  document.querySelectorAll("#signalButtons [data-index]").forEach(btn => {
    btn.addEventListener("click", () => {
      sendControl("set_mode", { mode: "MANUAL" });
      sendControl("set_index", { index: Number(btn.dataset.index) });
    });
  });
});
