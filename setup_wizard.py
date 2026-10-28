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
    QTextEdit,
    QPushButton,
    QMessageBox,
    QCheckBox,
)
from PyQt6.QtCore import Qt

from config import DEFAULT_CONFIG, Config


class SetupWizard(QWizard):
    """First-run wizard: network name, location, speedtest interval, Firebase config."""

    def __init__(self, config_path: str = "config.json"):
        super().__init__()
        self.config_path = config_path
        self.setWindowTitle("Speed Monitor - First Time Setup")
        self.setMinimumSize(500, 400)
        self.addPage(self._create_network_page())
        self.addPage(self._create_firebase_page())
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

        page.registerField("network_name*", self.network_input)
        page.registerField("location*", self.location_input)
        page.registerField("interval", self.interval_spin, "value")
        page.registerField("run_speedtests", self.run_speedtests_check)
        page.registerField("ping_host", self.ping_host_input)
        page.registerField("fallback_host", self.fallback_host_input)
        page.registerField("fallback_delay", self.fallback_delay_spin, "value")
        return page

    def _create_firebase_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Firebase Configuration")
        page.setSubTitle("Optional. Leave empty to store data locally only.")
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel("Firebase Project ID"))
        self.project_input = QLineEdit()
        self.project_input.setPlaceholderText("your-project-id")
        layout.addWidget(self.project_input)

        layout.addWidget(QLabel("Firebase API Key"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("AIza...")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.api_key_input)

        layout.addWidget(QLabel("Collection Name"))
        self.collection_input = QLineEdit("speed_records")
        layout.addWidget(self.collection_input)

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setPlainText(
            "How to get these values:\n"
            "1. Open Firebase Console: https://console.firebase.google.com\n"
            "2. Create/choose a project\n"
            "3. Project settings -> General -> Project ID & Web API Key\n"
            "4. Create a Firestore database\n"
            "5. Set security rules to allow writes for your authenticated users or use API key with proper rules."
        )
        layout.addWidget(help_text)

        page.registerField("project_id", self.project_input)
        page.registerField("api_key", self.api_key_input)
        page.registerField("collection", self.collection_input)
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
        )
        if self.field("project_id"):
            text += (
                f"\nFirebase Project: {self.field('project_id')}\n"
                f"Collection: {self.field('collection')}\n"
                f"Cloud sync: enabled\n"
            )
        else:
            text += "\nCloud sync: disabled (local only)\n"
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
        data["firebase_project_id"] = self.field("project_id") or ""
        data["firebase_api_key"] = self.field("api_key") or ""
        data["firebase_collection"] = self.field("collection") or "speed_records"

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


def run_wizard(config_path: str = "config.json") -> Config:
    app = QApplication(sys.argv)
    wizard = SetupWizard(config_path)
    if wizard.exec() != QWizard.DialogCode.Accepted:
        sys.exit(0)
    return wizard.save_config()


if __name__ == "__main__":
    cfg = run_wizard()
    print(cfg)
