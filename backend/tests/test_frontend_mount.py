"""The backend serves the built web UI when it exists, without shadowing the API."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_frontend


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/status")
    def status():
        return {"ok": True}

    return app


def test_no_build_no_mount(tmp_path):
    app = _app()
    assert mount_frontend(app, tmp_path / "missing") is False
    assert TestClient(app).get("/").status_code == 404


def test_serves_ui_and_keeps_api(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<title>Tello</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    app = _app()
    assert mount_frontend(app, tmp_path) is True
    client = TestClient(app)
    assert "Tello" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/api/status").json() == {"ok": True}
