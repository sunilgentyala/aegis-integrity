"""
Tests for the AEGIS REST API security controls: optional API-key auth,
upload size limits, and dynamic version reporting.

Each test explicitly sets (or clears) the relevant env vars and reloads
aegis.api.app so the module's env-driven globals (API_KEY, MAX_UPLOAD_BYTES,
_indexer's index dir) reflect that test's configuration, regardless of
what a previous test in the same session left behind.
"""

import importlib
import io

from fastapi.testclient import TestClient


def _reload_app(monkeypatch, tmp_path, api_key=None, max_upload_mb=None):
    if api_key is None:
        monkeypatch.delenv("AEGIS_API_KEY", raising=False)
    else:
        monkeypatch.setenv("AEGIS_API_KEY", api_key)
    if max_upload_mb is not None:
        monkeypatch.setenv("AEGIS_MAX_UPLOAD_MB", str(max_upload_mb))
    else:
        monkeypatch.delenv("AEGIS_MAX_UPLOAD_MB", raising=False)
    monkeypatch.setenv("AEGIS_INDEX_DIR", str(tmp_path / "idx"))
    monkeypatch.setenv("AEGIS_REPORT_DIR", str(tmp_path / "reports"))

    import aegis.api.app as app_module
    importlib.reload(app_module)
    return app_module


class TestAPIAuth:

    def test_health_never_requires_auth(self, monkeypatch, tmp_path):
        app_module = _reload_app(monkeypatch, tmp_path, api_key="secret123")
        client = TestClient(app_module.app)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_no_auth_required_when_key_unset(self, monkeypatch, tmp_path):
        app_module = _reload_app(monkeypatch, tmp_path, api_key=None)
        client = TestClient(app_module.app)
        resp = client.get("/corpus/summary")
        assert resp.status_code == 200

    def test_protected_route_rejects_missing_key(self, monkeypatch, tmp_path):
        app_module = _reload_app(monkeypatch, tmp_path, api_key="secret123")
        client = TestClient(app_module.app)
        resp = client.get("/corpus/summary")
        assert resp.status_code == 401

    def test_protected_route_rejects_wrong_key(self, monkeypatch, tmp_path):
        app_module = _reload_app(monkeypatch, tmp_path, api_key="secret123")
        client = TestClient(app_module.app)
        resp = client.get("/corpus/summary", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_protected_route_accepts_correct_key(self, monkeypatch, tmp_path):
        app_module = _reload_app(monkeypatch, tmp_path, api_key="secret123")
        client = TestClient(app_module.app)
        resp = client.get("/corpus/summary", headers={"X-API-Key": "secret123"})
        assert resp.status_code == 200


class TestAPIVersion:

    def test_openapi_version_matches_package(self, monkeypatch, tmp_path):
        from aegis import __version__
        app_module = _reload_app(monkeypatch, tmp_path)
        assert app_module.app.version == __version__


class TestUploadLimit:

    def test_oversized_upload_rejected(self, monkeypatch, tmp_path):
        app_module = _reload_app(monkeypatch, tmp_path, api_key=None, max_upload_mb=1)
        client = TestClient(app_module.app)
        oversized = io.BytesIO(b"x" * (2 * 1024 * 1024))  # 2MB > 1MB limit
        resp = client.post(
            "/corpus/add",
            files={"file": ("big.txt", oversized, "text/plain")},
        )
        assert resp.status_code == 413

    def test_undersized_upload_accepted(self, monkeypatch, tmp_path):
        app_module = _reload_app(monkeypatch, tmp_path, api_key=None, max_upload_mb=1)
        client = TestClient(app_module.app)
        small = io.BytesIO(b"Real document text about network security. " * 20)
        resp = client.post(
            "/corpus/add",
            files={"file": ("small.txt", small, "text/plain")},
        )
        assert resp.status_code == 200
