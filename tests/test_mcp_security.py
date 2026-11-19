"""Security regression tests for MCP tool semantics, path handling and the
offline guarantee.

No test here makes a real network call: every HTTP request is intercepted
and recorded, then refused.
"""

import asyncio
import os

import pytest
import requests

pytest.importorskip("mcp")

from click.testing import CliRunner  # noqa: E402

from aegis import mcp_server as m  # noqa: E402
from aegis.cli import cli  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def recorded_requests(monkeypatch):
    """Record every outgoing HTTP request and refuse it."""
    calls = []

    def _refuse(self, method, url, **kwargs):
        calls.append({"method": method, "url": url,
                      "params": kwargs.get("params"),
                      "allow_redirects": kwargs.get("allow_redirects", True)})
        raise requests.ConnectionError("network disabled in tests")

    monkeypatch.setattr(requests.Session, "request", _refuse)
    return calls


def _docx_with_title(path, title="Federated Anomaly Detection for Edge Networks"):
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph(title)
    d.add_paragraph("Abstract")
    d.add_paragraph("We propose a lightweight federated method for anomaly detection.")
    d.add_paragraph("References")
    d.add_paragraph('[1] J. Doe, "Federated learning at the edge," 2023, '
                    "doi:10.1000/xyz123.")
    d.save(str(path))
    return path


def _tools():
    return {t.name: t for t in asyncio.run(m.mcp.list_tools())}


# ---------------------------------------------------------------------------
# tool annotations
# ---------------------------------------------------------------------------

def test_no_tool_is_destructive():
    for name, tool in _tools().items():
        assert tool.annotations.destructiveHint is False, name


@pytest.mark.parametrize("name", [
    "aegis_analyze_paper", "aegis_check_citations",
    "aegis_check_guidelines", "aegis_index_add",
])
def test_tools_that_write_are_not_read_only(name):
    # analysis tools save an HTML report by default; index_add appends to the index
    assert _tools()[name].annotations.readOnlyHint is False


@pytest.mark.parametrize("name", ["aegis_compare_papers", "aegis_index_summary",
                                  "aegis_status"])
def test_pure_read_tools_are_read_only(name):
    assert _tools()[name].annotations.readOnlyHint is True


@pytest.mark.parametrize("name,expected", [
    ("aegis_analyze_paper", True), ("aegis_check_citations", True),
    ("aegis_status", True), ("aegis_check_guidelines", False),
    ("aegis_compare_papers", False), ("aegis_index_add", False),
])
def test_open_world_hint_matches_network_use(name, expected):
    assert _tools()[name].annotations.openWorldHint is expected


# ---------------------------------------------------------------------------
# path handling
# ---------------------------------------------------------------------------

def _symlink_or_skip(link, target):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available on this platform/user")


def test_symlink_inside_root_pointing_outside_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    link = root / "paper.txt"
    _symlink_or_skip(link, outside)
    monkeypatch.setenv("AEGIS_ALLOWED_ROOTS", str(root))
    assert "outside" in m._check_file(str(link))


def test_document_named_symlink_to_non_document_is_rejected(tmp_path):
    secret = tmp_path / "id_rsa"
    secret.write_text("PRIVATE KEY")
    link = tmp_path / "paper.txt"
    _symlink_or_skip(link, secret)
    # resolve() follows the link, so the real (non-document) suffix is checked
    assert "Unsupported file type" in m._check_file(str(link))


def test_directory_named_like_document_is_rejected(tmp_path):
    d = tmp_path / "paper.pdf"
    d.mkdir()
    assert "File not found" in m._check_file(str(d))


def test_missing_file_is_rejected(tmp_path):
    assert "File not found" in m._check_file(str(tmp_path / "nope.pdf"))


def test_multiple_allowed_roots(tmp_path, monkeypatch):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for d in (a, b, c):
        d.mkdir()
        (d / "p.txt").write_text("x")
    monkeypatch.setenv("AEGIS_ALLOWED_ROOTS", os.pathsep.join([str(a), str(b)]))
    assert m._check_file(str(a / "p.txt")) is None
    assert m._check_file(str(b / "p.txt")) is None
    assert "outside" in m._check_file(str(c / "p.txt"))


def test_sibling_prefix_is_not_inside_root(tmp_path, monkeypatch):
    # /x/papers must not allow /x/papers-private
    root = tmp_path / "papers"
    root.mkdir()
    sibling = tmp_path / "papers-private"
    sibling.mkdir()
    (sibling / "p.txt").write_text("x")
    monkeypatch.setenv("AEGIS_ALLOWED_ROOTS", str(root))
    assert "outside" in m._check_file(str(sibling / "p.txt"))


# ---------------------------------------------------------------------------
# offline guarantee
# ---------------------------------------------------------------------------

def test_mcp_skip_citations_requests_full_offline(tmp_path, monkeypatch):
    paper = tmp_path / "p.txt"
    paper.write_text("hello")
    seen = {}
    monkeypatch.setattr(m, "_run", lambda args, timeout=0: seen.setdefault("a", args) and "ok")
    monkeypatch.setenv("AEGIS_REPORT_DIR", str(tmp_path / "r"))
    m.aegis_analyze_paper(str(paper), skip_citations=True, html_report=False)
    assert "--no-citations" in seen["a"]
    assert "--offline" in seen["a"]


_FAST = ["--no-ai", "--no-semantic", "--no-stylometric", "--no-self-plagiarism",
         "--watermark-mode", "disabled"]


def test_cli_without_offline_sends_title_to_crossref(tmp_path, recorded_requests, monkeypatch):
    """Control case: proves the offline test below is meaningful."""
    monkeypatch.chdir(tmp_path)
    paper = _docx_with_title(tmp_path / "paper.docx")
    res = CliRunner().invoke(cli, ["analyze", str(paper), "--no-citations"] + _FAST)
    assert res.exit_code == 0, res.output
    titles = [c["params"].get("query.bibliographic") for c in recorded_requests
              if c["params"]]
    assert "Federated Anomaly Detection for Edge Networks" in titles


def test_cli_offline_makes_no_network_calls(tmp_path, recorded_requests, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paper = _docx_with_title(tmp_path / "paper.docx")
    res = CliRunner().invoke(cli, ["analyze", str(paper), "--offline"] + _FAST)
    assert res.exit_code == 0, res.output
    assert recorded_requests == []


def test_metadata_lookups_never_follow_redirects(tmp_path, recorded_requests, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paper = _docx_with_title(tmp_path / "paper.docx")
    CliRunner().invoke(cli, ["analyze", str(paper)] + _FAST)
    assert recorded_requests, "expected at least one (refused) lookup"
    for call in recorded_requests:
        assert call["allow_redirects"] is False, call["url"]
