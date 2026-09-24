"""
Tests for the v3.2 usability layer: shared data paths, the readiness check
(`aegis doctor` / GET /status), the browser UI route, offline analysis via
the API, report file naming from upload names, and the packaged MCP server.
"""

import importlib
import io

from click.testing import CliRunner
from fastapi.testclient import TestClient

from aegis import doctor, paths
from aegis.cli import cli


def _reload_app(monkeypatch, tmp_path, api_key=None):
    if api_key is None:
        monkeypatch.delenv("AEGIS_API_KEY", raising=False)
    else:
        monkeypatch.setenv("AEGIS_API_KEY", api_key)
    monkeypatch.setenv("AEGIS_INDEX_DIR", str(tmp_path / "idx"))
    monkeypatch.setenv("AEGIS_REPORT_DIR", str(tmp_path / "reports"))
    import aegis.api.app as app_module
    importlib.reload(app_module)
    return app_module


class TestPaths:

    def test_env_var_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AEGIS_INDEX_DIR", str(tmp_path / "custom"))
        assert paths.default_index_dir() == tmp_path / "custom"

    def test_legacy_cwd_index_is_kept(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AEGIS_INDEX_DIR", raising=False)
        (tmp_path / "aegis_index").mkdir()
        monkeypatch.chdir(tmp_path)
        assert paths.default_index_dir() == tmp_path / "aegis_index"

    def test_falls_back_to_aegis_home(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AEGIS_INDEX_DIR", raising=False)
        monkeypatch.delenv("AEGIS_REPORT_DIR", raising=False)
        monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
        monkeypatch.chdir(tmp_path)
        assert paths.default_index_dir() == tmp_path / "home" / "index"
        assert paths.default_report_dir() == tmp_path / "home" / "reports"

    def test_env_file_does_not_override_existing(self, monkeypatch, tmp_path):
        env = tmp_path / ".env"
        env.write_text('AEGIS_T1="from_file"\nAEGIS_T2=file2\n# comment\n', encoding="utf-8")
        monkeypatch.setenv("AEGIS_T2", "from_env")
        monkeypatch.delenv("AEGIS_T1", raising=False)
        paths.load_env_file(env)
        import os
        assert os.environ["AEGIS_T1"] == "from_file"
        assert os.environ["AEGIS_T2"] == "from_env"


class TestDoctor:

    def test_offline_checks_have_expected_shape(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AEGIS_INDEX_DIR", str(tmp_path / "empty"))
        checks = doctor.run_checks(offline=True)
        assert len(checks) >= 7
        assert all(c.status in (doctor.READY, doctor.LIMITED, doctor.MISSING) for c in checks)
        corpus = next(c for c in checks if "corpus" in c.name)
        assert corpus.status == doctor.LIMITED and corpus.fix
        crossref = next(c for c in checks if "Crossref" in c.name)
        assert crossref.status == doctor.LIMITED and "offline" in crossref.detail

    def test_every_non_ready_check_explains_itself(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AEGIS_INDEX_DIR", str(tmp_path / "empty"))
        for c in doctor.run_checks(offline=True):
            if c.status != doctor.READY:
                assert c.detail

    def test_corpus_count_read_from_meta(self, monkeypatch, tmp_path):
        idx = tmp_path / "idx"
        idx.mkdir()
        (idx / "corpus_meta.json").write_text(
            '[{"label":"a","added_at":"x"},{"label":"b","added_at":"y"}]', encoding="utf-8")
        monkeypatch.setenv("AEGIS_INDEX_DIR", str(idx))
        corpus = next(c for c in doctor.run_checks(offline=True) if "corpus" in c.name)
        assert corpus.status == doctor.READY and "2 document" in corpus.detail

    def test_pip_hint_matches_source_checkout(self):
        assert doctor.pip_hint("ml").startswith("pip install")
        assert "[ml]" in doctor.pip_hint("ml")
        assert "[" not in doctor.pip_hint()

    def test_cli_plain_output(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AEGIS_INDEX_DIR", str(tmp_path / "empty"))
        result = CliRunner().invoke(cli, ["doctor", "--plain", "--offline"])
        assert result.exit_code == 0, result.output
        assert "capabilities ready" in result.output
        assert "[WARN]" in result.output


class TestWebAPI:

    def test_root_serves_ui(self, monkeypatch, tmp_path):
        client = TestClient(_reload_app(monkeypatch, tmp_path).app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "AEGIS Integrity Checker" in resp.text

    def test_ui_has_no_external_assets(self, monkeypatch, tmp_path):
        # The UI must work fully offline: no CDN scripts, fonts or styles.
        html = TestClient(_reload_app(monkeypatch, tmp_path).app).get("/").text
        assert "<script src=" not in html
        assert "https://" not in html and "http://" not in html

    def test_ui_never_uses_innerhtml(self, monkeypatch, tmp_path):
        # Document text is untrusted; the UI builds DOM with textContent only.
        html = TestClient(_reload_app(monkeypatch, tmp_path).app).get("/").text
        assert "innerHTML" not in html and "outerHTML" not in html

    def test_health_reports_auth_without_leaking_paths(self, monkeypatch, tmp_path):
        client = TestClient(_reload_app(monkeypatch, tmp_path, api_key="k").app)
        body = client.get("/health").json()
        assert body["auth_required"] is True
        assert str(tmp_path) not in str(body)

    def test_status_requires_key_when_set(self, monkeypatch, tmp_path):
        client = TestClient(_reload_app(monkeypatch, tmp_path, api_key="k").app)
        assert client.get("/status?offline=true").status_code == 401
        resp = client.get("/status?offline=true", headers={"X-API-Key": "k"})
        assert resp.status_code == 200
        assert resp.json()["checks"]

    def test_offline_style_check_returns_html_and_real_name(self, monkeypatch, tmp_path):
        client = TestClient(_reload_app(monkeypatch, tmp_path).app)
        text = ("Results are shown in Eq. (1). We doesn't use contractions here. "
                "The colour of the model was analyzed. " * 20).encode()
        params = {
            "offline": "true", "include_html": "true", "run_ai": "false",
            "run_semantic": "false", "run_stylometric": "false",
            "run_self_plagiarism": "false", "run_watermark": "false",
            "run_coherence": "false", "run_citation_network": "false",
            "guidelines": "ieee",
        }
        resp = client.post("/analyze", params=params,
                           files={"file": ("My Draft: v2?.txt", io.BytesIO(text), "text/plain")})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["submission"] == "My Draft: v2?.txt"
        assert data["report_html"].startswith("<!DOCTYPE html>")
        # Report file name is sanitized from the upload name.
        assert data["report_path"].endswith("aegis_report_My_Draft_v2.html")
        status = data["detector_status"]
        assert status["venue_verification"]["status"] == "disabled"
        assert status["guideline_compliance"]["status"] == "completed"
        net = data["network_activity"]
        assert net["external_services_contacted"] == []
        assert net["document_content_transmitted"] is False


class TestMCPServer:

    def test_missing_file_gives_clear_message(self, tmp_path):
        from aegis import mcp_server
        msg = mcp_server.aegis_check_guidelines(str(tmp_path / "nope.pdf"))
        assert msg.startswith("File not found")

    def test_tools_registered(self):
        import asyncio
        from aegis import mcp_server
        names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
        assert {"aegis_analyze_paper", "aegis_check_citations", "aegis_check_guidelines",
                "aegis_compare_papers", "aegis_index_add", "aegis_index_summary",
                "aegis_status"} <= names

    def test_guidelines_tool_runs_end_to_end(self, monkeypatch, tmp_path):
        from aegis import mcp_server
        monkeypatch.setenv("AEGIS_INDEX_DIR", str(tmp_path / "idx"))
        monkeypatch.setenv("AEGIS_REPORT_DIR", str(tmp_path / "reports"))
        paper = tmp_path / "draft.txt"
        paper.write_text("We analyzed the colour of the data in Eq. (1). " * 30, encoding="utf-8")
        out = mcp_server.aegis_check_guidelines(str(paper), venues="IEEE")
        assert "exit code" not in out, out
        assert (tmp_path / "reports" / "draft_guidelines.html").exists()


class TestBodyTextFallback:

    def _doc(self, text, sections=()):
        from aegis.core.document import ParsedDocument
        return ParsedDocument(path="p.pdf", format="pdf", title=None, authors=[],
                              abstract=None, full_text=text, sections=list(sections),
                              references=[])

    def test_cuts_at_references_heading_when_sections_missed_it(self):
        body = "Intro text about the method. " * 40
        text = body + "\nReferences\n[1] A. Author, Title, Appl. Sci. 11 (7) (2021).\n"
        assert self._doc(text).body_text.strip() == body.strip()

    def test_front_matter_heading_does_not_empty_the_body(self):
        text = "References\n" + ("Real body text. " * 100)
        assert self._doc(text).body_text == text
