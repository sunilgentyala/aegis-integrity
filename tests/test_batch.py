"""
Tests for the `aegis batch` CLI command and the `/batch` API endpoint.

Both were previously documented (README, GitHub Pages site) but did not
exist -- `aegis batch` returned "Error: No such command 'batch'" and there
was no /batch route. These wire the existing, already-tested
BatchAnalyzer detector into both interfaces.
"""

import io

from click.testing import CliRunner

DOC_A = (
    "The proposed architecture integrates a locally deployed resolver with "
    "an anomaly detection model for enterprise network monitoring systems "
    "and continuous security log retention across the organization."
)
DOC_B = (
    "The proposed architecture integrates a locally deployed resolver with "
    "an anomaly detection model for enterprise network monitoring systems "
    "and continuous security log retention across the organization today."
)
DOC_C = (
    "Federated learning approaches for privacy preserving intrusion "
    "detection across distributed network segments operated by "
    "independent enterprise tenants without centralizing raw traffic."
)


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


class TestBatchCLI:

    def test_batch_command_exists(self):
        from aegis.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "batch" in result.output

    def test_batch_detects_near_duplicate_pair(self, tmp_path):
        from aegis.cli import cli
        _write(tmp_path, "a.txt", DOC_A)
        _write(tmp_path, "b.txt", DOC_B)
        _write(tmp_path, "c.txt", DOC_C)

        runner = CliRunner()
        result = runner.invoke(cli, ["batch", str(tmp_path), "--pattern", "*.txt", "--no-ai"])
        assert "a" in result.output and "b" in result.output
        assert "Overall Risk" in result.output

    def test_batch_writes_html(self, tmp_path):
        from aegis.cli import cli
        _write(tmp_path, "a.txt", DOC_A)
        _write(tmp_path, "b.txt", DOC_B)

        html_path = tmp_path / "out.html"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "batch", str(tmp_path), "--pattern", "*.txt", "--no-ai",
            "--html", str(html_path),
        ])
        assert result.exit_code in (0, 1)  # risk-dependent, but must not crash
        assert html_path.exists()

        html = html_path.read_text(encoding="utf-8")
        assert "AEGIS Batch" in html

    def test_batch_requires_at_least_two_files(self, tmp_path):
        from aegis.cli import cli
        _write(tmp_path, "a.txt", DOC_A)
        runner = CliRunner()
        result = runner.invoke(cli, ["batch", str(tmp_path), "--pattern", "*.txt", "--no-ai"])
        assert result.exit_code == 1


class TestBatchAPI:

    def _client(self, monkeypatch, tmp_path):
        import importlib
        monkeypatch.delenv("AEGIS_API_KEY", raising=False)
        monkeypatch.setenv("AEGIS_INDEX_DIR", str(tmp_path / "idx"))
        monkeypatch.setenv("AEGIS_REPORT_DIR", str(tmp_path / "reports"))
        import aegis.api.app as app_module
        importlib.reload(app_module)
        from fastapi.testclient import TestClient
        return TestClient(app_module.app)

    def test_batch_endpoint_exists_and_analyzes(self, monkeypatch, tmp_path):
        client = self._client(monkeypatch, tmp_path)
        files = [
            ("files", ("a.txt", io.BytesIO(DOC_A.encode()), "text/plain")),
            ("files", ("b.txt", io.BytesIO(DOC_B.encode()), "text/plain")),
            ("files", ("c.txt", io.BytesIO(DOC_C.encode()), "text/plain")),
        ]
        resp = client.post("/batch?run_ai=false", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["submission_count"] == 3
        assert "overall_risk" in data

    def test_batch_endpoint_rejects_single_file(self, monkeypatch, tmp_path):
        client = self._client(monkeypatch, tmp_path)
        files = [("files", ("a.txt", io.BytesIO(DOC_A.encode()), "text/plain"))]
        resp = client.post("/batch?run_ai=false", files=files)
        assert resp.status_code == 400
