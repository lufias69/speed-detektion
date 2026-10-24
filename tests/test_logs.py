import logging
import os
import tempfile
from logs import setup_logging


def test_setup_logging_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        log_file = os.path.join(tmp, "test.log")
        logger = setup_logging(log_file)
        logger.info("hello")

        for handler in logger.handlers:
            handler.flush()
            handler.close()

        assert os.path.exists(log_file)
        with open(log_file, "r") as f:
            assert "hello" in f.read()
