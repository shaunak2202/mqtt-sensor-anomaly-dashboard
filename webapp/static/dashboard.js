// Polls the Flask JSON API and renders one Chart.js line chart per sensor,
// with anomalous points drawn in red on top of the normal line.

const POLL_INTERVAL_MS = 4000;
const READING_LIMIT = 150;

const charts = {}; // sensor name -> Chart.js instance

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Request failed: ${url}`);
  return res.json();
}

function ensureCard(sensor) {
  if (document.getElementById(`card-${sensor}`)) return;

  const grid = document.getElementById("grid");
  const card = document.createElement("div");
  card.className = "card";
  card.id = `card-${sensor}`;
  card.innerHTML = `
    <h2><span>${sensor.replace("_", " ")}</span><span class="anomaly-badge" id="badge-${sensor}">0 anomalies</span></h2>
    <div class="stat-line" id="stat-${sensor}">loading...</div>
    <canvas id="chart-${sensor}"></canvas>
  `;
  grid.appendChild(card);

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

  const [readings, stats] = await Promise.all([
    fetchJSON(`/api/readings/${sensor}?limit=${READING_LIMIT}`),
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
