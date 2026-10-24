# main.py
import argparse
import logging
import signal
import sys
import threading
from datetime import datetime, timezone

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config, load_config
from db import get_engine, get_session
from logs import setup_logging
from monitor import Monitor
from web import create_app

logger = logging.getLogger("speedmonitor")


def build_app(config: Config):
    engine = get_engine(config.database_path)
    return create_app(config, engine)


def build_monitor(config: Config):
    engine = get_engine(config.database_path)
    # Each tick gets its own session; a Session is not thread-safe and the
    # scheduler runs ticks on its own thread (a speed test tick lasts up to 120 s).
    return Monitor(config, lambda: get_session(engine))


def main():
    parser = argparse.ArgumentParser(description="Speed Monitor")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config.log_path)

    logger.info("starting Speed Monitor")

    monitor = build_monitor(config)

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        monitor.tick,
        "interval",
        seconds=config.check_interval_seconds,
        id="speed_check",
        next_run_time=datetime.now(timezone.utc),  # first tick immediately
        replace_existing=True,
    )
    scheduler.start()

    app = build_app(config)

    stop_event = threading.Event()

    def handle_signal(signum, frame):
        logger.info("received signal %s, shutting down", signum)
        stop_event.set()
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        uvicorn.run(
            app,
            host=config.web_host,
            port=config.web_port,
            log_level="warning",
        )
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
