// static/app.js
const fmtDate = (iso) => new Date(iso).toLocaleString();
const fmtNum = (n, digits = 1) => n !== null && n !== undefined ? n.toFixed(digits) : '-';

const els = {
  status: document.getElementById('status-badge'),
  start: document.getElementById('start'),
  end: document.getElementById('end'),
  refresh: document.getElementById('refresh'),
  avgDown: document.getElementById('avg-download'),
  avgUp: document.getElementById('avg-upload'),
  avgPing: document.getElementById('avg-ping'),
  uptime: document.getElementById('uptime'),
  recordsBody: document.getElementById('records-body'),
};

let speedChart, pingChart;

function initCharts() {
  speedChart = new Chart(document.getElementById('speed-chart'), {
    type: 'line',
    data: { labels: [], datasets: [
      { label: 'Download Mbps', data: [], borderColor: '#007bff', fill: false },
      { label: 'Upload Mbps', data: [], borderColor: '#17a2b8', fill: false },
    ]},
    options: { responsive: true, scales: { y: { beginAtZero: true } }, plugins: { title: { display: true, text: 'Speed Over Time' } } }
  });

  pingChart = new Chart(document.getElementById('ping-chart'), {
    type: 'line',
    data: { labels: [], datasets: [
      { label: 'Ping ms', data: [], borderColor: '#ffc107', fill: false },
    ]},
    options: { responsive: true, scales: { y: { beginAtZero: true } }, plugins: { title: { display: true, text: 'Latency Over Time' } } }
  });
}

async function loadDashboard() {
  const params = new URLSearchParams();
  if (els.start.value) params.set('start', new Date(els.start.value).toISOString());
  if (els.end.value) params.set('end', new Date(els.end.value).toISOString());

  const [statusRes, recordsRes, statsRes] = await Promise.all([
    fetch('/api/status'),
    fetch('/api/records?' + params.toString()),
    fetch('/api/stats?' + params.toString()),
  ]);

  const status = await statusRes.json();
  const records = await recordsRes.json();
  const stats = await statsRes.json();

  const lastStatus = status.status || 'unknown';
  els.status.textContent = lastStatus;
  els.status.className = 'badge ' + lastStatus;

  els.avgDown.textContent = fmtNum(stats.avg_download) + ' Mbps';
  els.avgUp.textContent = fmtNum(stats.avg_upload) + ' Mbps';
  els.avgPing.textContent = fmtNum(stats.avg_ping, 0) + ' ms';
  els.uptime.textContent = (stats.uptime_percent ?? 0).toFixed(1) + '%';

  const labels = records.slice().reverse().map(r => fmtDate(r.timestamp));
  speedChart.data.labels = labels;
  speedChart.data.datasets[0].data = records.slice().reverse().map(r => r.download_mbps);
  speedChart.data.datasets[1].data = records.slice().reverse().map(r => r.upload_mbps);
  speedChart.update();

  pingChart.data.labels = labels;
  pingChart.data.datasets[0].data = records.slice().reverse().map(r => r.ping_ms);
  pingChart.update();

  els.recordsBody.innerHTML = records.slice(0, 100).map(r => `
    <tr>
      <td>${fmtDate(r.timestamp)}</td>
      <td>${r.ssid || '-'}</td>
      <td>${r.status}</td>
      <td>${fmtNum(r.ping_ms, 0)}</td>
      <td>${fmtNum(r.download_mbps)}</td>
      <td>${fmtNum(r.upload_mbps)}</td>
    </tr>
  `).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  const now = new Date();
  const yesterday = new Date(now - 24 * 60 * 60 * 1000);
  const toInput = (d) => d.toISOString().slice(0, 16);
  els.end.value = toInput(now);
  els.start.value = toInput(yesterday);

  initCharts();
  loadDashboard();
  els.refresh.addEventListener('click', loadDashboard);
  setInterval(loadDashboard, 30000);
});
