import json
import logging
import os
import sys
import threading
import tkinter as tk
from datetime import datetime, timezone, timedelta
from tkinter import ttk, messagebox, filedialog

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo

from config import Config, DEFAULT_CONFIG
from secure_config import decrypt_config, save_encrypted_config
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
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def _localize(dt: datetime, tz_name: str) -> datetime:
    if dt is None:
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz_name))


class SyncWorker(threading.Thread):
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


class TkSettingsDialog(tk.Toplevel):
    def __init__(self, parent, config: Config):
        super().__init__(parent)
        self.config = config
        self.title("Settings")
        self.geometry("420x400")
        self.result = None

        frame = ttk.Frame(self, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        self.fields = {}
        rows = [
            ("Network / ISP", "network_name"),
            ("Location", "location"),
            ("Connection Type", "connection_type"),
            ("Speedtest Interval (s)", "speed_test_interval_seconds"),
            ("Run Speedtests", "run_speed_tests"),
            ("Ping Host", "ping_host"),
            ("Fallback Host", "fallback_host"),
            ("Fallback Delay (s)", "fallback_delay_seconds"),
            ("Timezone", "timezone"),
            ("Firebase Project ID", "firebase_project_id"),
            ("Firebase API Key", "firebase_api_key"),
            ("Collection", "firebase_collection"),
        ]

        for i, (label, key) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            value = getattr(config, key, "")
            if key == "run_speed_tests":
                var = tk.BooleanVar(value=bool(value))
                widget = ttk.Checkbutton(frame, variable=var)
                widget.grid(row=i, column=1, sticky=tk.W, pady=2)
                self.fields[key] = var
            else:
                entry = ttk.Entry(frame)
                entry.insert(0, str(value))
                entry.grid(row=i, column=1, sticky=tk.EW, pady=2)
                self.fields[key] = entry

        frame.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.RIGHT, padx=5)

    def _save(self):
        data = {**DEFAULT_CONFIG, **self.config.__dict__}
        for key, widget in self.fields.items():
            if isinstance(widget, tk.BooleanVar):
                data[key] = widget.get()
            else:
                data[key] = widget.get()
        try:
            data["speed_test_interval_seconds"] = int(data["speed_test_interval_seconds"])
            data["fallback_delay_seconds"] = int(data["fallback_delay_seconds"])
            data["run_speed_tests"] = bool(data["run_speed_tests"])
        except ValueError:
            messagebox.showerror("Invalid input", "Interval and delay must be numbers.")
            return
        self.result = Config(**data)
        save_encrypted_config(self.result)
        self.destroy()


class TkDesktopApp:
    def __init__(self, config: Config):
        self.config = config
        self.root = tk.Tk()
        self.root.title(f"Speed Monitor - {config.network_name} @ {config.location}")
        self.root.geometry("900x600")

        self.engine = get_engine(config.database_path)
        self.monitor = Monitor(config, lambda: get_session(self.engine))
        self.sync = FirestoreSync(config)
        if self.sync.enabled():
            self.sync_worker = SyncWorker(self.sync)
            self.sync_worker.start()
        else:
            self.sync_worker = None

        self._build_ui()
        self._schedule_tick()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        header = ttk.Frame(self.root, padding="10")
        header.pack(fill=tk.X)
        ttk.Label(header, text="Speed Monitor", font=("Segoe UI", 18, "bold")).pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="CHECKING")
        self.status_label = ttk.Label(header, textvariable=self.status_var, font=("Segoe UI", 12, "bold"))
        self.status_label.pack(side=tk.RIGHT)

        sub = ttk.Frame(self.root)
        sub.pack(fill=tk.X, padx=10)
        conn = self.config.connection_type or "Unknown"
        ttk.Label(sub, text=f"{self.config.network_name} • {self.config.location} • {conn}").pack(side=tk.LEFT)

        cards = ttk.Frame(self.root, padding="10")
        cards.pack(fill=tk.X)
        self.card_vars = {}
        for i, (title, unit) in enumerate([
            ("Avg Download", "Mbps"),
            ("Avg Upload", "Mbps"),
            ("Avg Ping", "ms"),
            ("Uptime", "%"),
            ("Connection", ""),
            ("Cloud Sync", ""),
            ("Last Check", ""),
        ]):
            frame = ttk.LabelFrame(cards, text=title, padding="10")
            frame.grid(row=i // 4, column=i % 4, padx=5, pady=5, sticky=tk.NSEW)
            var = tk.StringVar(value="-")
            ttk.Label(frame, textvariable=var, font=("Segoe UI", 14, "bold")).pack()
            self.card_vars[title] = (var, unit)
        cards.columnconfigure(tuple(range(4)), weight=1)

        btn_frame = ttk.Frame(self.root, padding="10")
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Refresh Now", command=self._do_tick).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Run Speedtest", command=self._run_speedtest_manual).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Settings", command=self._open_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Sync to Cloud", command=self._manual_sync).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export CSV", command=self._export_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Analytics", command=self._open_analytics).pack(side=tk.LEFT, padx=5)

        # Filter bar
        filter_frame = ttk.Frame(self.root, padding="5")
        filter_frame.pack(fill=tk.X)
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=2)
        self.filter_var = tk.StringVar(value="Today")
        self.filter_combo = ttk.Combobox(filter_frame, textvariable=self.filter_var, values=["Today", "Last 7 days", "Last 14 days", "Last 30 days", "Custom range"], state="readonly", width=14)
        self.filter_combo.pack(side=tk.LEFT, padx=2)
        self.filter_combo.bind("<<ComboboxSelected>>", self._on_filter_changed)

        ttk.Label(filter_frame, text="From:").pack(side=tk.LEFT, padx=(10, 2))
        self.start_date = tk.StringVar()
        self.start_entry = ttk.Entry(filter_frame, textvariable=self.start_date, width=12)
        self.start_entry.pack(side=tk.LEFT, padx=2)
        self.start_entry.config(state="disabled")

        ttk.Label(filter_frame, text="To:").pack(side=tk.LEFT, padx=(10, 2))
        self.end_date = tk.StringVar()
        self.end_entry = ttk.Entry(filter_frame, textvariable=self.end_date, width=12)
        self.end_entry.pack(side=tk.LEFT, padx=2)
        self.end_entry.config(state="disabled")

        self.apply_btn = ttk.Button(filter_frame, text="Apply", command=self._apply_filter)
        self.apply_btn.pack(side=tk.LEFT, padx=(10, 2))
        self.apply_btn.config(state="disabled")

        table_frame = ttk.Frame(self.root, padding="10")
        table_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(table_frame, text="Recent Records", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        cols = ("Date", "Time", "SSID", "Conn", "Status", "Ping (ms)", "TTL (hops)", "Size (B)", "Min (ms)", "Max (ms)", "Avg (ms)", "Loss %", "Down (Mbps)", "Up (Mbps)", "Synced")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=75, anchor=tk.CENTER)
        self.tree.column("Date", width=80)
        self.tree.column("Time", width=70)
        self.tree.column("SSID", width=100)
        self.tree.column("Conn", width=70)
        self.tree.column("Status", width=60)

        # Scrollbar for table
        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)

        log_frame = ttk.Frame(self.root, padding="10")
        log_frame.pack(fill=tk.X)
        ttk.Label(log_frame, text="Recent Logs", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        self.log_text = tk.Text(log_frame, height=6, state=tk.DISABLED, bg="#0f172a", fg="#e2e8f0")
        self.log_text.pack(fill=tk.X)

    def _schedule_tick(self):
        self._do_tick()
        self.root.after(self.config.check_interval_seconds * 1000, self._schedule_tick)

    def _do_tick(self):
        def tick():
            try:
                record = self.monitor.tick()
                self.root.after(0, lambda: self._on_record(record))
            except Exception as exc:
                logger.warning("tick failed: %s", exc)
        threading.Thread(target=tick, daemon=True).start()

    def _on_record(self, record: SpeedRecord):
        if record.status == "online":
            self.status_var.set("ONLINE")
            self.status_label.config(foreground="green")
        else:
            self.status_var.set("OFFLINE")
            self.status_label.config(foreground="red")
        self.card_vars["Connection"][0].set(record.connection_type or "Unknown")
        self.card_vars["Cloud Sync"][0].set("on" if self.sync.enabled() else "off")
        local_ts = _localize(record.timestamp, self.config.timezone)
        self.card_vars["Last Check"][0].set(local_ts.strftime("%H:%M:%S"))
        self._refresh_stats()
        self._refresh_table()
        self._append_log(f"{record.status} ping={record.ping_ms} type={record.connection_type}")

    def _on_filter_changed(self, event=None):
        choice = self.filter_var.get()
        is_custom = choice == "Custom range"
        state = "normal" if is_custom else "disabled"
        self.start_entry.config(state=state)
        self.end_entry.config(state=state)
        self.apply_btn.config(state="normal" if is_custom else "disabled")
        if not is_custom:
            self._refresh_table()
            self._refresh_stats()

    def _parse_date(self, text: str):
        try:
            return datetime.strptime(text.strip(), "%Y-%m-%d").date()
        except Exception:
            return None

    def _apply_filter(self, event=None):
        self._refresh_table()
        self._refresh_stats()

    def _get_filter_range(self):
        tz = ZoneInfo(self.config.timezone)
        now = datetime.now(tz)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        choice = self.filter_var.get()

        if choice == "Today":
            start = today
            end = now
        elif choice == "Last 7 days":
            start = today - timedelta(days=6)
            end = now
        elif choice == "Last 14 days":
            start = today - timedelta(days=13)
            end = now
        elif choice == "Last 30 days":
            start = today - timedelta(days=29)
            end = now
        else:
            start_text = self.start_date.get()
            end_text = self.end_date.get()
            start_dt = self._parse_date(start_text)
            end_dt = self._parse_date(end_text)
            if start_dt is None or end_dt is None:
                messagebox.showwarning("Invalid range", "Please enter dates in YYYY-MM-DD format.")
                return None, None
            if start_dt > end_dt:
                messagebox.showwarning("Invalid range", "Start date must be before or equal to end date.")
                return None, None
            start = datetime.combine(start_dt, datetime.min.time(), tz)
            end = datetime.combine(end_dt, datetime.max.time(), tz)
        return start, end

    def _refresh_stats(self):
        session = get_session(self.engine)
        start, end = self._get_filter_range()
        if start is None:
            return
        try:
            stats = get_stats(session, start, end)
            self.card_vars["Avg Download"][0].set(f"{stats['avg_download']:.2f}" if stats['avg_download'] else "-")
            self.card_vars["Avg Upload"][0].set(f"{stats['avg_upload']:.2f}" if stats['avg_upload'] else "-")
            self.card_vars["Avg Ping"][0].set(f"{stats['avg_ping']:.1f}" if stats['avg_ping'] else "-")
            self.card_vars["Uptime"][0].set(f"{stats['uptime_percent']:.1f}")
        finally:
            session.close()

    def _refresh_table(self):
        session = get_session(self.engine)
        start, end = self._get_filter_range()
        if start is None:
            return
        try:
            rows = get_records_in_range(session, start, end, 1000)
        finally:
            session.close()
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            local_ts = _localize(r.timestamp, self.config.timezone)
            self.tree.insert("", tk.END, values=(
                local_ts.strftime("%Y-%m-%d"),
                local_ts.strftime("%H:%M:%S"),
                r.ssid or "",
                r.connection_type or "",
                r.status.upper(),
                f"{r.ping_ms:.1f}" if r.ping_ms else "-",
                str(r.ping_ttl) if r.ping_ttl is not None else "-",
                str(r.packet_size) if r.packet_size is not None else "-",
                f"{r.ping_min_ms:.1f}" if r.ping_min_ms is not None else "-",
                f"{r.ping_max_ms:.1f}" if r.ping_max_ms is not None else "-",
                f"{r.ping_avg_ms:.1f}" if r.ping_avg_ms is not None else "-",
                f"{r.packet_loss_percent:.0f}" if r.packet_loss_percent is not None else "-",
                f"{r.download_mbps:.2f}" if r.download_mbps is not None else "-",
                f"{r.upload_mbps:.2f}" if r.upload_mbps is not None else "-",
                "Yes" if r.cloud_id else "No",
            ))

    def _append_log(self, message: str):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} | {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _open_settings(self):
        dialog = TkSettingsDialog(self.root, self.config)
        self.root.wait_window(dialog)
        if dialog.result:
            self.config = dialog.result
            self.monitor.config = self.config
            self.sync.config = self.config
            self.root.title(f"Speed Monitor - {self.config.network_name} @ {self.config.location}")

    def _run_speedtest_manual(self):
        """Run a speedtest on demand and save the result to the database."""
        self._append_log("Manual speedtest requested...")

        # Show modal progress dialog while the speedtest runs
        progress = tk.Toplevel(self.root)
        progress.title("Speedtest")
        progress.geometry("320x100")
        progress.transient(self.root)
        progress.grab_set()
        progress.protocol("WM_DELETE_WINDOW", lambda: None)
        ttk.Label(progress, text="Running speedtest, please wait...", font=("Segoe UI", 11)).pack(pady=(15, 5))
        ttk.Label(progress, text="This may take up to 2 minutes.", font=("Segoe UI", 9)).pack()
        self.root.config(cursor="watch")
        progress.update()

        def close_progress():
            progress.destroy()
            self.root.config(cursor="")

        def do_speedtest():
            from speedtester import SpeedTester
            from checker import check_connection
            from db import add_record
            import traceback

            try:
                logger.info("manual speedtest: starting")
                tester = SpeedTester(
                    cli_path=self.config.speed_test_cli_path,
                    cooldown_file="data/.speedtest_last_run_manual",
                )
                logger.info("manual speedtest: SpeedTester created, cli=%s", tester.cli_path)
                speed = tester.run(force=True)
                logger.info("manual speedtest: raw result=%s", speed)
                check = check_connection(self.config)
                logger.info("manual speedtest: ping status=%s down=%s up=%s", check.status, check.ping_ms, None)
                record = SpeedRecord(
                    timestamp=check.timestamp,
                    ssid=check.ssid,
                    connection_type=check.connection_type,
                    adapter=check.adapter,
                    status=check.status,
                    ping_ms=check.ping_ms,
                    ping_ttl=check.ping_ttl,
                    packet_size=check.packet_size,
                    ping_min_ms=check.ping_min_ms,
                    ping_max_ms=check.ping_max_ms,
                    ping_avg_ms=check.ping_avg_ms,
                    packet_loss_percent=check.packet_loss_percent,
                )
                if speed and record.status == "online":
                    record.download_mbps = speed.download_mbps
                    record.upload_mbps = speed.upload_mbps
                    record.ping_ms = speed.ping_ms
                    logger.info("manual speedtest: assigned down=%s up=%s", speed.download_mbps, speed.upload_mbps)
                else:
                    logger.warning("manual speedtest: no speed result or status=%s", record.status)

                session = get_session(self.engine)
                try:
                    add_record(session, record)
                    logger.info("manual speedtest: record saved id=%s", record.id)
                finally:
                    session.close()

                self.root.after(0, lambda: self._on_record(record))
                self._append_log(
                    f"Speedtest saved: down={record.download_mbps:.2f} Mbps, up={record.upload_mbps:.2f} Mbps"
                )
            except Exception as exc:
                tb = traceback.format_exc()
                logger.error("manual speedtest failed: %s\n%s", exc, tb)
                self.root.after(0, lambda msg=str(exc): self._append_log(f"Speedtest failed: {msg}"))
            finally:
                self.root.after(0, close_progress)

        threading.Thread(target=do_speedtest, daemon=True).start()

    def _manual_sync(self):
        if not self.sync.enabled():
            messagebox.showwarning("Sync disabled", "Configure Firebase in Settings first.")
            return
        count = self.sync.run_once()
        self._refresh_table()
        messagebox.showinfo("Sync", f"Synced {count} records.")

    def _export_csv(self):
        start, end = self._get_filter_range()
        if start is None:
            return
        default_name = f"speed_records_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=default_name, filetypes=[("CSV Files", "*.csv")])
        if not path:
            return

        import csv
        session = get_session(self.engine)
        try:
            rows = get_records_in_range(session, start, end)
        finally:
            session.close()

        headers = [
            "timestamp", "ssid", "connection_type", "adapter", "status",
            "ping_ms", "ping_ttl", "packet_size", "ping_min_ms", "ping_max_ms",
            "ping_avg_ms", "packet_loss_percent", "download_mbps", "upload_mbps",
            "error_message", "synced", "cloud_id",
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in rows:
                local_ts = _localize(r.timestamp, self.config.timezone)
                writer.writerow([
                    local_ts.isoformat(),
                    r.ssid or "",
                    r.connection_type or "",
                    r.adapter or "",
                    r.status,
                    r.ping_ms,
                    r.ping_ttl,
                    r.packet_size,
                    r.ping_min_ms,
                    r.ping_max_ms,
                    r.ping_avg_ms,
                    r.packet_loss_percent,
                    r.download_mbps,
                    r.upload_mbps,
                    r.error_message or "",
                    "Yes" if r.cloud_id else "No",
                    r.cloud_id or "",
                ])
        messagebox.showinfo("Exported", f"Saved {len(rows)} records to {path}")

    def _open_analytics(self):
        from analytics import analyze_daily
        start, end = self._get_filter_range()
        if start is None:
            return
        session = get_session(self.engine)
        try:
            rows = get_records_in_range(session, start, end)
        finally:
            session.close()
        if not rows:
            messagebox.showinfo("Analytics", "No records found in selected range.")
            return

        summaries = analyze_daily(rows, self.config.timezone)

        dialog = tk.Toplevel(self.root)
        dialog.title("Daily Analytics")
        dialog.geometry("900x500")

        cols = ("Date", "Day", "Online (h)", "Offline (h)", "Uptime %", "Avg Ping", "Avg TTL", "Avg Loss %")
        tree = ttk.Treeview(dialog, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=90, anchor=tk.CENTER)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        for s in summaries:
            tree.insert("", tk.END, values=(
                s.date.strftime("%Y-%m-%d"),
                s.day_name,
                f"{s.online_hours:.1f}",
                f"{s.offline_hours:.1f}",
                f"{s.uptime_percent:.1f}",
                f"{s.avg_ping_ms:.1f}" if s.avg_ping_ms is not None else "-",
                f"{s.avg_ttl:.1f}" if s.avg_ttl is not None else "-",
                f"{s.avg_packet_loss:.1f}" if s.avg_packet_loss is not None else "-",
            ))

        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=5)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.sync_worker:
            self.sync_worker.stop()
        self.root.destroy()


def _config_needs_setup(config: Config) -> bool:
    return not config.network_name or not config.location


def run_tk_desktop(config_path: str = "config.json"):
    if not os.path.exists(config_path):
        print("Config not found. Please run the PyQt6 wizard first or create config.json manually.", file=sys.stderr)
        sys.exit(1)
    config = decrypt_config(config_path)
    for key, value in DEFAULT_CONFIG.items():
        if not hasattr(config, key):
            setattr(config, key, value)
    if _config_needs_setup(config):
        print("Config incomplete. Please run the PyQt6 wizard first.", file=sys.stderr)
        sys.exit(1)
    setup_logging(config.log_path)
    app = TkDesktopApp(config)
    app.run()


if __name__ == "__main__":
    run_tk_desktop()
