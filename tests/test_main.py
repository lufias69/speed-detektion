from unittest.mock import patch, MagicMock
from config import Config
from main import build_monitor, build_app


def test_build_app_returns_fastapi_instance():
    cfg = Config(database_path=":memory:", web_port=5000)
    app = build_app(cfg)
    from fastapi import FastAPI
    assert isinstance(app, FastAPI)
