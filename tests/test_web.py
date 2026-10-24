from fastapi.testclient import TestClient
from config import Config
from db import get_engine
from web import create_app


def test_status_endpoint():
    cfg = Config(database_path=":memory:", web_port=5000)
    engine = get_engine(cfg.database_path)
    app = create_app(cfg, engine)
    client = TestClient(app)
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unknown"
    assert "last_record" in data
