import json
import os
import stat
import sys

from PyQt6.QtWidgets import (
    QApplication,
    QWizard,
    QWizardPage,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QMessageBox,
    QCheckBox,
)
from PyQt6.QtCore import Qt

from config import DEFAULT_CONFIG, Config


class SetupWizard(QWizard):
    """First-run wizard: network name, location, and ping config.

    Firebase sync is optional and can be configured later via Settings.
    """

    def __init__(self, config_path: str = "config.json"):
        super().__init__()
        self.config_path = config_path
        self.setWindowTitle("Speed Monitor - First Time Setup")
        self.setMinimumSize(500, 400)
        self.addPage(self._create_network_page())
        self.addPage(self._create_summary_page())
        self.setButtonText(QWizard.WizardButton.FinishButton, "Save & Start")

    def _create_network_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Network & Location")
        page.setSubTitle("Identify where this device is monitoring from.")
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel("Network / ISP Name *"))
        self.network_input = QLineEdit()
        self.network_input.setPlaceholderText("e.g. Office-Indihome")
        layout.addWidget(self.network_input)

        layout.addWidget(QLabel("Location *"))
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("e.g. Jakarta - Lantai 2")
        layout.addWidget(self.location_input)

        layout.addWidget(QLabel("Speedtest Interval (seconds)"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(300, 86400)
        self.interval_spin.setValue(3600)
        self.interval_spin.setSingleStep(300)
        layout.addWidget(self.interval_spin)

        self.run_speedtests_check = QCheckBox("Run speedtests (uncheck for ping-only mode)")
        self.run_speedtests_check.setChecked(False)
        layout.addWidget(self.run_speedtests_check)

        layout.addWidget(QLabel("Ping Host (primary)"))
        self.ping_host_input = QLineEdit("8.8.8.8")
        layout.addWidget(self.ping_host_input)

        layout.addWidget(QLabel("Fallback Ping Host"))
        self.fallback_host_input = QLineEdit("8.8.4.4")
        layout.addWidget(self.fallback_host_input)

        layout.addWidget(QLabel("Fallback Delay (seconds)"))
        self.fallback_delay_spin = QSpinBox()
        self.fallback_delay_spin.setRange(0, 300)
        self.fallback_delay_spin.setValue(10)
        layout.addWidget(self.fallback_delay_spin)

        layout.addWidget(QLabel("Timezone"))
        self.timezone_input = QLineEdit("Asia/Makassar")
        self.timezone_input.setPlaceholderText("e.g. Asia/Makassar")
        layout.addWidget(self.timezone_input)

        page.registerField("network_name*", self.network_input)
        page.registerField("location*", self.location_input)
        page.registerField("interval", self.interval_spin, "value")
        page.registerField("run_speedtests", self.run_speedtests_check)
        page.registerField("ping_host", self.ping_host_input)
        page.registerField("fallback_host", self.fallback_host_input)
        page.registerField("fallback_delay", self.fallback_delay_spin, "value")
        page.registerField("timezone", self.timezone_input)
        return page

    def _create_summary_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Ready")
        page.setSubTitle("Review and save your settings.")
        layout = QVBoxLayout(page)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.summary_label)
        page.setFinalPage(True)
        page.initializePage = self._update_summary
        return page

    def _update_summary(self):
        text = (
            f"Network: {self.field('network_name')}\n"
            f"Location: {self.field('location')}\n"
            f"Speedtest interval: {self.field('interval')} seconds\n"
            f"Ping host: {self.field('ping_host')}\n"
            f"Fallback host: {self.field('fallback_host')} (delay {self.field('fallback_delay')}s)\n"
            f"Timezone: {self.field('timezone')}\n"
            f"\nCloud sync can be enabled later in Settings.\n"
        )
        self.summary_label.setText(text)

    def save_config(self) -> Config:
        data = {**DEFAULT_CONFIG}
        data["network_name"] = self.field("network_name") or ""
        data["location"] = self.field("location") or ""
        data["speed_test_interval_seconds"] = self.field("interval")
        data["run_speed_tests"] = bool(self.field("run_speedtests"))
        data["ping_host"] = self.field("ping_host") or "8.8.8.8"
        data["fallback_host"] = self.field("fallback_host") or "8.8.4.4"
        data["fallback_delay_seconds"] = self.field("fallback_delay")
        data["timezone"] = self.field("timezone") or "Asia/Makassar"

        _write_config(self.config_path, data)

        return Config(**data)


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


def run_wizard(config_path: str = "config.json", app: QApplication = None) -> Config:
    """Run the setup wizard. If an existing QApplication is provided, use it."""
    created_app = False
    if app is None:
        app = QApplication(sys.argv)
        created_app = True
    wizard = SetupWizard(config_path)
    result = wizard.exec()
    if result != QWizard.DialogCode.Accepted:
        if created_app:
            sys.exit(0)
        raise RuntimeError("Setup cancelled")
    return wizard.save_config()


if __name__ == "__main__":
    cfg = run_wizard()
    print(cfg)
