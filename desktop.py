import json
import logging
import os
import stat
import sys
import threading
from datetime import datetime, timezone, timedelta

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QLineEdit,
    QDialog,
    QFormLayout,
    QSpinBox,
    QTextEdit,
    QStatusBar,
    QCheckBox,
    QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont

from config import Config, DEFAULT_CONFIG, load_config
from db import (
    SpeedRecord,
    get_engine,
    get_session,
    get_recent_records,
    get_stats,
)
from logs import setup_logging
from monitor import Monitor
from cloud_sync import FirestoreSync

logger = logging.getLogger("speedmonitor")

# Modern, compact stylesheet inspired by clean dashboard design.
APP_STYLESHEET = """
QMainWindow {
    background-color: #f5f7fa;
}
QWidget {
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: #2c3e50;
}
QPushButton {
    background-color: #2563eb;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #1d4ed8;
}
QPushButton:pressed {
    background-color: #1e40af;
}
QLineEdit, QSpinBox {
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 10px;
    background: white;
}
QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #2563eb;
}
QTableWidget {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    gridline-color: #e2e8f0;
}
QTableWidget::item {
    padding: 8px;
    border-bottom: 1px solid #f1f5f9;
}
QHeaderView::section {
    background-color: #f1f5f9;
    padding: 10px;
    border: none;
    font-weight: 700;
    color: #475569;
}
QTextEdit {
    background-color: #0f172a;
    color: #e2e8f0;
    border-radius: 8px;
    padding: 8px;
    font-family: Consolas, "Courier New", monospace;
    font-size: 12px;
}
QCheckBox {
    spacing: 8px;
}
"""


def _write_config(path: str, data: dict):
    """Write config.json with owner-only permissions where supported."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


class SyncWorker(threading.Thread):
    """Run cloud sync in background so UI stays responsive."""

    def __init__(self, sync: FirestoreSync, interval_seconds: int = 300):
        super().__init__(daemon=True)
        self.sync = sync
        self.interval = interval_seconds
        self.running = True

    def run(self):
        while self.running:
            try:
                count = self.sync.run_once()
                if count:
                    logger.info("synced %d records to cloud", count)
            except Exception as exc:
                logger.warning("background sync error: %s", exc)
            deadline = datetime.now(timezone.utc) + timedelta(seconds=self.interval)
            while self.running and datetime.now(timezone.utc) < deadline:
                import time
                time.sleep(1)

    def stop(self):
        self.running = False


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        self.config = config
        layout = QFormLayout(self)
        layout.setVerticalSpacing(12)
        layout.setHorizontalSpacing(16)

        self.network_input = QLineEdit(config.network_name)
        self.location_input = QLineEdit(config.location)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(300, 86400)
        self.interval_spin.setValue(config.speed_test_interval_seconds)
        self.run_speedtests_check = QCheckBox("Run speedtests")
        self.run_speedtests_check.setChecked(config.run_speed_tests)
        self.ping_host_input = QLineEdit(config.ping_host)
        self.fallback_host_input = QLineEdit(config.fallback_host)
        self.fallback_delay_spin = QSpinBox()
        self.fallback_delay_spin.setRange(0, 300)
        self.fallback_delay_spin.setValue(config.fallback_delay_seconds)
        self.project_input = QLineEdit(config.firebase_project_id)
        self.api_key_input = QLineEdit(config.firebase_api_key)
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.collection_input = QLineEdit(config.firebase_collection)

        layout.addRow("Network / ISP", self.network_input)
        layout.addRow("Location", self.location_input)
        layout.addRow("Speedtest Interval (s)", self.interval_spin)
        layout.addRow(self.run_speedtests_check)
        layout.addRow("Ping Host", self.ping_host_input)
        layout.addRow("Fallback Host", self.fallback_host_input)
        layout.addRow("Fallback Delay (s)", self.fallback_delay_spin)
        layout.addRow("Firebase Project ID", self.project_input)
        layout.addRow("Firebase API Key", self.api_key_input)
        layout.addRow("Collection", self.collection_input)

        buttons = QHBoxLayout()
        buttons.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addRow(buttons)

    def updated_config(self) -> Config:
        data = {
            **DEFAULT_CONFIG,
            **self.config.__dict__,
            "network_name": self.network_input.text(),
            "location": self.location_input.text(),
            "speed_test_interval_seconds": self.interval_spin.value(),
            "run_speed_tests": self.run_speedtests_check.isChecked(),
            "ping_host": self.ping_host_input.text(),
            "fallback_host": self.fallback_host_input.text(),
            "fallback_delay_seconds": self.fallback_delay_spin.value(),
            "firebase_project_id": self.project_input.text(),
            "firebase_api_key": self.api_key_input.text(),
            "firebase_collection": self.collection_input.text(),
        }
        return Config(**data)


class MainWindow(QMainWindow):
    new_record = pyqtSignal(object)

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.setWindowTitle(f"Speed Monitor - {config.network_name} @ {config.location}")
        self.setMinimumSize(960, 680)

        self.engine = get_engine(config.database_path)
        self.monitor = Monitor(config, lambda: get_session(self.engine))

        self.sync = FirestoreSync(config)
        if self.sync.enabled():
            self.sync_worker = SyncWorker(self.sync)
            self.sync_worker.start()
        else:
            self.sync_worker = None

        self._build_ui()
        self._setup_scheduler()
        self.new_record.connect(self._on_new_record)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QHBoxLayout()
        title = QLabel("Speed Monitor")
        title_font = QFont("Segoe UI", 22, QFont.Weight.Bold)
        title.setFont(title_font)
        title.setStyleSheet("color: #1e293b;")
        subtitle = QLabel(f"{self.config.network_name} • {self.config.location}")
        subtitle.setStyleSheet("color: #64748b; font-size: 13px;")
        header_left = QVBoxLayout()
        header_left.setSpacing(2)
        header_left.addWidget(title)
        header_left.addWidget(subtitle)
        header.addLayout(header_left)
        header.addStretch()

        self.status_badge = QLabel("CHECKING")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setStyleSheet(
            "background-color: #f59e0b; color: white; padding: 8px 18px; "
            "border-radius: 16px; font-weight: 700; font-size: 13px;"
        )
        header.addWidget(self.status_badge)
        layout.addLayout(header)

        # Summary cards
        cards = QGridLayout()
        cards.setSpacing(12)
        self.avg_down = self._summary_card("Avg Download", "-", "Mbps")
        self.avg_up = self._summary_card("Avg Upload", "-", "Mbps")
        self.avg_ping = self._summary_card("Avg Ping", "-", "ms")
        self.uptime = self._summary_card("Uptime", "-", "%")
        self.synced_label = self._summary_card("Cloud Sync", "off", "")
        self.last_check_label = self._summary_card("Last Check", "-", "")

        cards.addWidget(self.avg_down, 0, 0)
        cards.addWidget(self.avg_up, 0, 1)
        cards.addWidget(self.avg_ping, 0, 2)
        cards.addWidget(self.uptime, 0, 3)
        cards.addWidget(self.synced_label, 1, 0)
        cards.addWidget(self.last_check_label, 1, 1)
        layout.addLayout(cards)

        # Actions
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("↻ Refresh Now")
        refresh_btn.clicked.connect(self._do_tick)
        settings_btn = QPushButton("⚙ Settings")
        settings_btn.clicked.connect(self._open_settings)
        sync_btn = QPushButton("↑ Sync to Cloud")
        sync_btn.clicked.connect(self._manual_sync)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(settings_btn)
        btn_layout.addWidget(sync_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # History table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Time", "SSID", "Status", "Ping", "Down", "Up", "Synced"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.table, stretch=1)

        # Log view
        log_label = QLabel("Recent Logs")
        log_label.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        layout.addWidget(log_label)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(110)
        layout.addWidget(self.log_view)

        self.statusBar().showMessage("Ready")

    def _summary_card(self, title: str, value: str, unit: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #e2e8f0; "
            "border-radius: 10px; padding: 12px; }"
        )
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)
        layout.setSpacing(4)
        layout.setContentsMargins(14, 10, 14, 10)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        value_lbl = QLabel(f"{value} {unit}".strip())
        value_lbl.setStyleSheet("color: #0f172a; font-size: 20px; font-weight: 700;")
        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        return card

    def _setup_scheduler(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._do_tick)
        self.timer.start(self.config.check_interval_seconds * 1000)
        QTimer.singleShot(500, self._do_tick)

    def _do_tick(self):
        def tick():
            try:
                record = self.monitor.tick()
                self.new_record.emit(record)
            except Exception as exc:
                logger.warning("tick failed: %s", exc)
        threading.Thread(target=tick, daemon=True).start()

    def _on_new_record(self, record: SpeedRecord):
        if record.status == "online":
            self.status_badge.setText("ONLINE")
            self.status_badge.setStyleSheet(
                "background-color: #10b981; color: white; padding: 8px 18px; "
                "border-radius: 16px; font-weight: 700; font-size: 13px;"
            )
        else:
            self.status_badge.setText("OFFLINE")
            self.status_badge.setStyleSheet(
                "background-color: #ef4444; color: white; padding: 8px 18px; "
                "border-radius: 16px; font-weight: 700; font-size: 13px;"
            )
        self.last_check = record.timestamp
        self._refresh_table()
        self._refresh_stats()

    def _refresh_stats(self):
        session = get_session(self.engine)
        try:
            stats = get_stats(session)
            self._set_card_value(self.avg_down, stats["avg_download"], "{:.2f}", "Mbps")
            self._set_card_value(self.avg_up, stats["avg_upload"], "{:.2f}", "Mbps")
            self._set_card_value(self.avg_ping, stats["avg_ping"], "{:.1f}", "ms")
            self._set_card_value(self.uptime, stats["uptime_percent"], "{:.1f}", "%")
            self._set_card_value(self.synced_label, "on" if self.sync.enabled() else "off", None, "")
            if hasattr(self, "last_check"):
                self._set_card_value(
                    self.last_check_label,
                    self.last_check.strftime("%H:%M:%S"),
                    None,
                    "",
                )
        finally:
            session.close()

    def _set_card_value(self, card: QFrame, value, fmt: str, unit: str):
        value_lbl = card.layout().itemAt(1).widget()
        if value is None:
            value_lbl.setText("-" if unit else "-")
        elif fmt:
            value_lbl.setText(f"{fmt.format(value)} {unit}".strip())
        else:
            value_lbl.setText(f"{value} {unit}".strip())

    def _refresh_table(self):
        session = get_session(self.engine)
        try:
            rows = get_recent_records(session, 50)
        finally:
            session.close()

        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r.timestamp.strftime("%Y-%m-%d %H:%M:%S")))
            self.table.setItem(i, 1, QTableWidgetItem(r.ssid or ""))
            status_item = QTableWidgetItem(r.status.upper())
            if r.status == "online":
                status_item.setForeground(self._color("#10b981"))
            else:
                status_item.setForeground(self._color("#ef4444"))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 2, status_item)
            self.table.setItem(i, 3, QTableWidgetItem(self._fmt_num(r.ping_ms, "{:.1f}")))
            self.table.setItem(i, 4, QTableWidgetItem(self._fmt_num(r.download_mbps, "{:.2f}")))
            self.table.setItem(i, 5, QTableWidgetItem(self._fmt_num(r.upload_mbps, "{:.2f}")))
            sync_item = QTableWidgetItem("Yes" if r.cloud_id else "No")
            sync_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 6, sync_item)

    def _fmt_num(self, value, fmt: str) -> str:
        return fmt.format(value) if value is not None else "-"

    def _color(self, hex_color: str):
        from PyQt6.QtGui import QColor
        return QColor(hex_color)

    def _open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.config = dialog.updated_config()
        _write_config("config.json", self.config.__dict__)
        self.monitor.config = self.config
        self.sync.config = self.config
        self.setWindowTitle(f"Speed Monitor - {self.config.network_name} @ {self.config.location}")
        self.timer.setInterval(self.config.check_interval_seconds * 1000)
        QMessageBox.information(self, "Saved", "Settings saved. Changes take effect immediately.")

    def _manual_sync(self):
        if not self.sync.enabled():
            QMessageBox.warning(self, "Sync disabled", "Configure Firebase in Settings first.")
            return
        count = self.sync.run_once()
        self._refresh_table()
        QMessageBox.information(self, "Sync", f"Synced {count} records.")

    def closeEvent(self, event):
        if self.sync_worker:
            self.sync_worker.stop()
        event.accept()


def _config_needs_setup(config: Config) -> bool:
    return not config.network_name or not config.location


def run_desktop(config_path: str = "config.json"):
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)

    if not os.path.exists(config_path):
        from setup_wizard import run_wizard
        config = run_wizard(config_path)
    else:
        config = load_config(config_path)
        for key, value in DEFAULT_CONFIG.items():
            if not hasattr(config, key):
                setattr(config, key, value)
        if _config_needs_setup(config):
            from setup_wizard import run_wizard
            config = run_wizard(config_path)

    setup_logging(config.log_path)

    window = MainWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_desktop()
