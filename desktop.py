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
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal

from config import Config, DEFAULT_CONFIG, load_config
from db import (
    SpeedRecord,
    get_engine,
    get_session,
    get_recent_records,
    get_records_in_range,
    get_stats,
)
from logs import setup_logging
from monitor import Monitor
from cloud_sync import FirestoreSync

logger = logging.getLogger("speedmonitor")


def _write_config(path: str, data: dict):
    """Write config.json with owner-only permissions where supported."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        # Fallback for platforms without POSIX permission support.
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
        self.setMinimumWidth(400)
        self.config = config
        layout = QFormLayout(self)

        self.network_input = QLineEdit(config.network_name)
        self.location_input = QLineEdit(config.location)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(300, 86400)
        self.interval_spin.setValue(config.speed_test_interval_seconds)
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
        layout.addRow("Ping Host", self.ping_host_input)
        layout.addRow("Fallback Host", self.fallback_host_input)
        layout.addRow("Fallback Delay (s)", self.fallback_delay_spin)
        layout.addRow("Firebase Project ID", self.project_input)
        layout.addRow("Firebase API Key", self.api_key_input)
        layout.addRow("Collection", self.collection_input)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addRow(buttons)

    def updated_config(self) -> Config:
        data = {
            **DEFAULT_CONFIG,
            **self.config.__dict__,
            "network_name": self.network_input.text(),
            "location": self.location_input.text(),
            "speed_test_interval_seconds": self.interval_spin.value(),
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
        self.setMinimumSize(900, 600)

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

        # Top status bar
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Status: checking...")
        self.status_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.last_check_label = QLabel("Last check: -")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.last_check_label)
        layout.addLayout(status_layout)

        # Summary cards
        summary_layout = QHBoxLayout()
        self.avg_down = QLabel("Avg Down: -")
        self.avg_up = QLabel("Avg Up: -")
        self.avg_ping = QLabel("Avg Ping: -")
        self.uptime = QLabel("Uptime: -")
        self.synced_label = QLabel("Cloud sync: -")
        for w in (self.avg_down, self.avg_up, self.avg_ping, self.uptime, self.synced_label):
            w.setStyleSheet("background: #f0f0f0; padding: 10px; border-radius: 6px;")
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            summary_layout.addWidget(w)
        layout.addLayout(summary_layout)

        # Actions
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh Now")
        refresh_btn.clicked.connect(self._do_tick)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._open_settings)
        sync_btn = QPushButton("Sync to Cloud")
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
        layout.addWidget(self.table)

        # Log view
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(120)
        layout.addWidget(self.log_view)

        self.statusBar().showMessage("Ready")

    def _setup_scheduler(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._do_tick)
        self.timer.start(self.config.check_interval_seconds * 1000)
        # first tick shortly after UI shows
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
        color = "green" if record.status == "online" else "red"
        self.status_label.setText(f"Status: <span style='color:{color}'>{record.status.upper()}</span>")
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        self.last_check_label.setText(f"Last check: {record.timestamp.strftime('%H:%M:%S')}")
        self._refresh_table()
        self._refresh_stats()

    def _refresh_stats(self):
        session = get_session(self.engine)
        try:
            stats = get_stats(session)
            self.avg_down.setText(f"Avg Down\n{stats['avg_download']:.2f if stats['avg_download'] else '-'} Mbps")
            self.avg_up.setText(f"Avg Up\n{stats['avg_upload']:.2f if stats['avg_upload'] else '-'} Mbps")
            self.avg_ping.setText(f"Avg Ping\n{stats['avg_ping']:.2f if stats['avg_ping'] else '-'} ms")
            self.uptime.setText(f"Uptime\n{stats['uptime_percent']}%")
            self.synced_label.setText(f"Cloud sync\n{'on' if self.sync.enabled() else 'off'}")
        finally:
            session.close()

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
            status_item.setForeground(
                self.palette().color(self.palette().ColorRole.Link) if r.status == "online"
                else self.palette().color(self.palette().ColorRole.Highlight)
            )
            self.table.setItem(i, 2, status_item)
            self.table.setItem(i, 3, QTableWidgetItem(f"{r.ping_ms:.1f}" if r.ping_ms else ""))
            self.table.setItem(i, 4, QTableWidgetItem(f"{r.download_mbps:.2f}" if r.download_mbps else ""))
            self.table.setItem(i, 5, QTableWidgetItem(f"{r.upload_mbps:.2f}" if r.upload_mbps else ""))
            self.table.setItem(i, 6, QTableWidgetItem("Yes" if r.cloud_id else "No"))

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


def run_desktop(config_path: str = "config.json"):
    app = QApplication(sys.argv)

    if not os.path.exists(config_path):
        from setup_wizard import run_wizard
        config = run_wizard(config_path)
    else:
        config = load_config(config_path)
        # ensure new fields exist
        for key, value in DEFAULT_CONFIG.items():
            if not hasattr(config, key):
                setattr(config, key, value)

    setup_logging(config.log_path)

    window = MainWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_desktop()
