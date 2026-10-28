from datetime import datetime, timedelta, timezone

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QWidget,
    QSizePolicy,
    QMessageBox,
)
from PyQt6.QtCore import Qt

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from matplotlib.patches import Patch
except ImportError:
    FigureCanvas = None
    Figure = None

from config import Config
from db import get_session, get_records_in_range
from analytics import analyze_daily


class AnalyticsDialog(QDialog):
    def __init__(self, config: Config, engine, parent=None):
        super().__init__(parent)
        self.config = config
        self.engine = engine
        self.setWindowTitle("Daily Analytics")
        self.setMinimumSize(1100, 750)

        layout = QVBoxLayout(self)

        # Controls
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Range:"))
        self.range_combo = QComboBox()
        self.range_combo.addItems(["Last 7 days", "Last 14 days", "Last 30 days"])
        self.range_combo.currentTextChanged.connect(self._load_data)
        self.load_btn = QPushButton("Load")
        self.load_btn.clicked.connect(self._load_data)
        self.summary_label = QLabel("")
        controls.addWidget(self.range_combo)
        controls.addWidget(self.load_btn)
        controls.addStretch()
        controls.addWidget(self.summary_label)
        layout.addLayout(controls)

        # Chart
        if FigureCanvas and Figure:
            self.figure = Figure(figsize=(10, 4))
            self.canvas = FigureCanvas(self.figure)
            self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self.canvas, stretch=2)
        else:
            self.figure = None
            self.canvas = None
            layout.addWidget(QLabel("Matplotlib not installed; chart unavailable."))

        # Day table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Date", "Day", "Online (h)", "Offline (h)", "Uptime %", "Avg Ping (ms)", "Avg TTL", "Avg Loss %"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.cellClicked.connect(self._show_day_detail)
        layout.addWidget(self.table, stretch=1)

        # Detail panel
        self.detail_label = QLabel("Click a day above to see online/offline hours.")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: #64748b; padding: 8px; background: #f8fafc; border-radius: 6px;")
        layout.addWidget(self.detail_label)

        self.summaries = []
        self._load_data()

    def _get_range(self):
        tz = self.config.timezone
        now = datetime.now(ZoneInfo(tz))
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        choice = self.range_combo.currentText()
        if choice == "Last 7 days":
            days = 7
        elif choice == "Last 14 days":
            days = 14
        else:
            days = 30
        start = today - timedelta(days=days - 1)
        end = now
        return start, end

    def _load_data(self):
        start, end = self._get_range()
        session = get_session(self.engine)
        try:
            records = get_records_in_range(session, start, end)
        finally:
            session.close()

        if not records:
            self.summary_label.setText("No data for selected range.")
            self.table.setRowCount(0)
            if self.canvas:
                self.figure.clear()
                self.canvas.draw()
            return

        self.summaries = analyze_daily(records, self.config.timezone)
        self._render_table()
        self._render_chart()
        total_online = round(sum(s.online_hours for s in self.summaries), 2)
        total_offline = round(sum(s.offline_hours for s in self.summaries), 2)
        self.summary_label.setText(f"Total online: {total_online}h | Total offline: {total_offline}h over {len(self.summaries)} days")

    def _render_table(self):
        self.table.setRowCount(len(self.summaries))
        for i, s in enumerate(self.summaries):
            self.table.setItem(i, 0, QTableWidgetItem(s.date.strftime("%Y-%m-%d")))
            self.table.setItem(i, 1, QTableWidgetItem(s.day_name))
            self.table.setItem(i, 2, QTableWidgetItem(f"{s.online_hours:.2f}"))
            self.table.setItem(i, 3, QTableWidgetItem(f"{s.offline_hours:.2f}"))
            self.table.setItem(i, 4, QTableWidgetItem(f"{s.uptime_percent:.1f}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{s.avg_ping_ms:.1f}" if s.avg_ping_ms is not None else "-"))
            self.table.setItem(i, 6, QTableWidgetItem(f"{s.avg_ttl:.1f}" if s.avg_ttl is not None else "-"))
            self.table.setItem(i, 7, QTableWidgetItem(f"{s.avg_packet_loss:.1f}" if s.avg_packet_loss is not None else "-"))

    def _render_chart(self):
        if not self.canvas:
            return
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        dates = [s.date.strftime("%m-%d") for s in self.summaries]
        online = [s.online_hours for s in self.summaries]
        offline = [s.offline_hours for s in self.summaries]

        x = range(len(dates))
        width = 0.35
        ax.bar([i - width / 2 for i in x], online, width, label="Online (h)", color="#10b981")
        ax.bar([i + width / 2 for i in x], offline, width, label="Offline (h)", color="#ef4444")
        ax.set_xticks(x)
        ax.set_xticklabels(dates, rotation=45, ha="right")
        ax.set_ylabel("Hours")
        ax.set_title("Daily Online vs Offline Hours")
        ax.legend()
        self.figure.tight_layout()
        self.canvas.draw()

    def _show_day_detail(self, row, col):
        if row < 0 or row >= len(self.summaries):
            return
        s = self.summaries[row]
        online_hours = ", ".join(sorted(set(s.online_times))) if s.online_times else "-"
        offline_hours = ", ".join(sorted(set(s.offline_times))) if s.offline_times else "-"
        text = (
            f"Details for {s.date.strftime('%Y-%m-%d')} ({s.day_name}):\n"
            f"Online hours: {s.online_hours:.2f}h | Offline hours: {s.offline_hours:.2f}h | Uptime: {s.uptime_percent:.1f}%\n"
            f"Online times: {online_hours}\n"
            f"Offline times: {offline_hours}\n"
            f"Avg ping: {s.avg_ping_ms:.1f}ms | Avg TTL: {s.avg_ttl:.1f} | Avg loss: {s.avg_packet_loss:.1f}%"
        )
        self.detail_label.setText(text)


# Helper for ZoneInfo used in _get_range
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
