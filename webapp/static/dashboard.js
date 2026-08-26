// Polls the Flask JSON API and renders one Chart.js line chart per sensor,
// with anomalous points drawn in red on top of the normal line. Each card
// also has a time-range selector and a window/threshold tuning form that
// calls the settings API.

const POLL_INTERVAL_MS = 4000;
const READING_LIMIT = 300;

const RANGE_OPTIONS = [
  { label: "Last 15m", ms: 15 * 60 * 1000 },
  { label: "Last 1h", ms: 60 * 60 * 1000 },
  { label: "Last 6h", ms: 6 * 60 * 60 * 1000 },
  { label: "Last 24h", ms: 24 * 60 * 60 * 1000 },
  { label: "All", ms: null },
];

const charts = {}; // sensor name -> Chart.js instance
const selectedRangeMs = {}; // sensor name -> ms (or null for "all")

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Request failed: ${url} ${text}`);
  }
  return res.json();
}

function ensureCard(sensor) {
  if (document.getElementById(`card-${sensor}`)) return;
  if (!(sensor in selectedRangeMs)) selectedRangeMs[sensor] = RANGE_OPTIONS[1].ms; // default: last 1h

  const grid = document.getElementById("grid");
  const card = document.createElement("div");
  card.className = "card";
  card.id = `card-${sensor}`;

  const rangeOptionsHtml = RANGE_OPTIONS.map(
    (opt, i) => `<option value="${i}" ${opt.ms === selectedRangeMs[sensor] ? "selected" : ""}>${opt.label}</option>`
  ).join("");

  card.innerHTML = `
    <h2><span>${sensor.replace("_", " ")}</span><span class="anomaly-badge" id="badge-${sensor}">0 anomalies</span></h2>
    <div class="stat-line" id="stat-${sensor}">loading...</div>
    <div class="controls">
      <label>Range:
        <select id="range-${sensor}" class="range-select">${rangeOptionsHtml}</select>
      </label>
      <label>Window: <input type="number" id="window-${sensor}" min="2" value="30" class="tune-input"></label>
      <label>Threshold: <input type="number" step="0.1" id="threshold-${sensor}" min="0.1" value="3.0" class="tune-input"></label>
      <button id="apply-${sensor}" class="apply-btn">Apply</button>
      <span class="apply-status" id="apply-status-${sensor}"></span>
    </div>
    <canvas id="chart-${sensor}"></canvas>
  `;
  grid.appendChild(card);

  document.getElementById(`range-${sensor}`).addEventListener("change", (e) => {
    selectedRangeMs[sensor] = RANGE_OPTIONS[parseInt(e.target.value, 10)].ms;
    refreshSensor(sensor);
  });

  document.getElementById(`apply-${sensor}`).addEventListener("click", () => applySettings(sensor));

  const ctx = document.getElementById(`chart-${sensor}`).getContext("2d");
  charts[sensor] = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: sensor,
          data: [],
          borderColor: "#4da3ff",
          backgroundColor: "rgba(77, 163, 255, 0.1)",
          pointRadius: 0,
          tension: 0.2,
          borderWidth: 1.5,
        },
        {
          label: "anomaly",
          data: [],
          borderColor: "transparent",
          backgroundColor: "#ff4d5e",
          pointRadius: 4,
          pointStyle: "circle",
          showLine: false,
        },
      ],
    },
    options: {
      responsive: true,
      animation: false,
      scales: {
        x: { ticks: { color: "#9aa0a6", maxTicksLimit: 6 }, grid: { color: "#22252f" } },
        y: { ticks: { color: "#9aa0a6" }, grid: { color: "#22252f" } },
      },
      plugins: {
        legend: { display: false },
      },
    },
  });

  loadSettingsIntoForm(sensor);
}

async function loadSettingsIntoForm(sensor) {
  try {
    const settings = await fetchJSON(`/api/settings/${sensor}`);
    document.getElementById(`window-${sensor}`).value = settings.window;
    document.getElementById(`threshold-${sensor}`).value = settings.threshold;
  } catch (err) {
    console.error("Failed to load settings for", sensor, err);
  }
}

async function applySettings(sensor) {
  const statusEl = document.getElementById(`apply-status-${sensor}`);
  const window_ = parseInt(document.getElementById(`window-${sensor}`).value, 10);
  const threshold = parseFloat(document.getElementById(`threshold-${sensor}`).value);

  statusEl.textContent = "saving...";
  try {
    await fetchJSON(`/api/settings/${sensor}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ window: window_, threshold: threshold }),
    });
    statusEl.textContent = "saved \u2713";
    setTimeout(() => (statusEl.textContent = ""), 2000);
  } catch (err) {
    console.error("Failed to save settings for", sensor, err);
    statusEl.textContent = "failed to save";
  }
}

function formatTime(ts) {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString();
  } catch {
    return ts;
  }
}

async function refreshSensor(sensor) {
  ensureCard(sensor);

  const rangeMs = selectedRangeMs[sensor];
  let readingsUrl = `/api/readings/${sensor}?limit=${READING_LIMIT}`;
  if (rangeMs) {
    const since = new Date(Date.now() - rangeMs).toISOString();
    readingsUrl += `&since=${encodeURIComponent(since)}`;
  }

  const [readings, stats] = await Promise.all([
    fetchJSON(readingsUrl),
    fetchJSON(`/api/stats/${sensor}`),
  ]);

  const labels = readings.map((r) => formatTime(r.timestamp));
  const values = readings.map((r) => r.value);
  const anomalyPoints = readings.map((r) => (r.is_anomaly ? r.value : null));

  const chart = charts[sensor];
  chart.data.labels = labels;
  chart.data.datasets[0].data = values;
  chart.data.datasets[1].data = anomalyPoints;
  chart.update();

  const badge = document.getElementById(`badge-${sensor}`);
  badge.textContent = `${stats.anomaly_count} anomalies`;

  const statLine = document.getElementById(`stat-${sensor}`);
  const latest = stats.latest_value !== null ? stats.latest_value.toFixed(2) : "--";
  statLine.textContent = `latest: ${latest}  |  total readings: ${stats.total_readings}  |  last anomaly: ${stats.latest_anomaly_timestamp ? formatTime(stats.latest_anomaly_timestamp) : "none yet"}`;
}

async function refreshAll() {
  try {
    const sensors = await fetchJSON("/api/sensors");
    document.getElementById("empty").style.display = sensors.length ? "none" : "block";
    await Promise.all(sensors.map(refreshSensor));
  } catch (err) {
    console.error("Dashboard refresh failed:", err);
  }
}

refreshAll();
setInterval(refreshAll, POLL_INTERVAL_MS);
