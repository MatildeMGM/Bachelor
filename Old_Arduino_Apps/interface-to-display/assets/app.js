let socket;

function $(id) { return document.getElementById(id); }

function pad16(s) {
  s = (s || "").replace(/\r?\n/g, " ");
  if (s.length > 16) return s.slice(0, 16);
  return s;
}

function padTo16Preview(s) {
  s = pad16(s);
  while (s.length < 16) s += " ";
  return s;por
}

function nowTime() {
  const d = new Date();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

function setConnBadge(text, kind) {
  const b = $("connBadge");
  b.textContent = text;
  b.style.color = kind === "ok" ? "rgba(255,255,255,0.92)" : "rgba(255,255,255,0.70)";
  b.style.borderColor =
    kind === "ok" ? "rgba(43,228,167,0.45)" :
    kind === "err" ? "rgba(255,90,122,0.45)" :
    "rgba(255,255,255,0.12)";
  b.style.background =
    kind === "ok" ? "rgba(43,228,167,0.12)" :
    kind === "err" ? "rgba(255,90,122,0.10)" :
    "rgba(0,0,0,0.18)";
}

function setStatus(msg, kind = "info") {
  const dot = $("statusDot");
  const text = $("status");
  text.textContent = msg;

  if (kind === "ok") {
    dot.style.background = "var(--ok)";
    dot.style.boxShadow = "0 0 0 4px rgba(43,228,167,0.16)";
    text.style.color = "var(--muted)";
  } else if (kind === "err") {
    dot.style.background = "var(--err)";
    dot.style.boxShadow = "0 0 0 4px rgba(255,90,122,0.16)";
    text.style.color = "var(--muted)";
  } else {
    dot.style.background = "var(--warn)";
    dot.style.boxShadow = "0 0 0 4px rgba(255,204,102,0.16)";
    text.style.color = "var(--muted)";
  }
}

function updateCountersAndPreview() {
  const l1 = pad16($("line1").value);
  const l2 = pad16($("line2").value);

  $("c1").textContent = l1.length;
  $("c2").textContent = l2.length;

  $("p1").textContent = padTo16Preview(l1);
  $("p2").textContent = padTo16Preview(l2);
}

function addHistory(line1, line2) {
  const box = $("history");
  const item = document.createElement("div");
  item.className = "hitem";
  item.innerHTML = `
    <div class="hmeta">${nowTime()}</div>
    <div class="htext">${padTo16Preview(line1)}\n${padTo16Preview(line2)}</div>
  `;
  item.addEventListener("click", () => {
    $("line1").value = line1;
    $("line2").value = line2;
    updateCountersAndPreview();
  });
  box.prepend(item);
}

function sendToLCD() {
  const line1 = pad16($("line1").value);
  const line2 = pad16($("line2").value);

  setStatus("Sending…", "info");
  socket.emit("lcd_write", { line1, line2 });
}

document.addEventListener("DOMContentLoaded", () => {
  // Match the Arduino example style
  socket = io(`http://${window.location.host}`);

  socket.on("connect", () => {
    setConnBadge("Connected", "ok");
    setStatus("Ready.", "ok");
  });

  socket.on("disconnect", () => {
    setConnBadge("Disconnected", "err");
    setStatus("Disconnected from board.", "err");
  });

  socket.on("lcd_ack", (data) => {
    setStatus(`Sent: "${data.line1}" | "${data.line2}"`, "ok");
    addHistory(data.line1 || "", data.line2 || "");
  });

  socket.on("lcd_error", (data) => {
    setStatus(`Error: ${data.error}`, "err");
  });

  // Inputs
  $("line1").addEventListener("input", updateCountersAndPreview);
  $("line2").addEventListener("input", updateCountersAndPreview);

  // Buttons
  $("sendBtn").addEventListener("click", sendToLCD);
  $("clearBtn").addEventListener("click", () => {
    $("line1").value = "";
    $("line2").value = "";
    updateCountersAndPreview();
    sendToLCD();
  });

  // Preset chips
  for (const btn of document.querySelectorAll(".chip")) {
    btn.addEventListener("click", () => {
      $("line1").value = btn.dataset.l1 || "";
      $("line2").value = btn.dataset.l2 || "";
      updateCountersAndPreview();
      sendToLCD();
    });
  }

  // Ctrl/Cmd + Enter to send
  document.addEventListener("keydown", (e) => {
    const isEnter = e.key === "Enter";
    const mod = e.ctrlKey || e.metaKey;
    if (isEnter && mod) {
      e.preventDefault();
      sendToLCD();
    }
  });

  updateCountersAndPreview();
});