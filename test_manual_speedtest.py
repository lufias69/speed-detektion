"""Standalone test for manual speedtest flow.

Run this on the target device (e.g. Orange Pi) to verify:
1. speedtest-cli is available and returns JSON.
2. A ping check succeeds.
3. The combined record can be saved to the database.
"""

import logging
import os
import sys
import traceback

# Ensure logs directory exists for this test script
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/test_manual_speedtest.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("test_manual_speedtest")


def main():
    try:
        from config import Config
        from secure_config import decrypt_config
        from checker import check_connection
        from speedtester import SpeedTester
        from db import SpeedRecord, add_record, get_engine, get_session

        config_path = "config.json"
        if not os.path.exists(config_path):
            logger.error("config.json not found")
            sys.exit(1)

        config = decrypt_config(config_path)
        logger.info("Config loaded: network=%s location=%s", config.network_name, config.location)
        logger.info("speed_test_cli_path=%s", config.speed_test_cli_path)

        tester = SpeedTester(
            cli_path=config.speed_test_cli_path,
            cooldown_file="data/.speedtest_last_run_manual",
        )
        logger.info("SpeedTester created")
        logger.info("speedtest-cli available: %s", tester.is_available())

        logger.info("Running speedtest (force=True)...")
        speed = tester.run(force=True)
        logger.info("Speedtest raw result: %s", speed)

        logger.info("Running ping check...")
        check = check_connection(config)
        logger.info("Ping status=%s ping_ms=%s", check.status, check.ping_ms)

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
            logger.info(
                "Assigned speed values: down=%.2f up=%.2f ping=%.1f",
                speed.download_mbps,
                speed.upload_mbps,
                speed.ping_ms,
            )
        else:
            logger.warning("No speed result or status not online; record will be ping-only")

        engine = get_engine(config.database_path)
        session = get_session(engine)
        try:
            add_record(session, record)
            logger.info("Record saved with id=%s", record.id)
        finally:
            session.close()

        logger.info(
            "FINAL: status=%s down=%s up=%s ping=%s",
            record.status,
            record.download_mbps,
            record.upload_mbps,
            record.ping_ms,
        )
    except Exception as exc:
        logger.error("Test failed: %s\n%s", exc, traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
