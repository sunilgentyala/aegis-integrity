"""Regression tests for the MCP server input hardening."""

import pytest

pytest.importorskip("mcp")

from aegis import mcp_server as m  # noqa: E402


def test_rejects_non_document_extension(tmp_path):
    secret = tmp_path / "id_rsa"
    secret.write_text("PRIVATE KEY")
    assert "Unsupported file type" in m._check_file(str(secret))


@pytest.mark.parametrize("suffix", [".txt", ".md", ".MD"])
def test_accepts_text_document(tmp_path, suffix):
    f = tmp_path / ("paper" + suffix)
    f.write_text("hello")
    assert m._check_file(str(f)) is None


def test_allowed_roots_blocks_outside(tmp_path, monkeypatch):
    inside = tmp_path / "ok"
    inside.mkdir()
    outside = tmp_path / "other.txt"
    outside.write_text("x")
    monkeypatch.setenv("AEGIS_ALLOWED_ROOTS", str(inside))
    assert "outside" in m._check_file(str(outside))
    (inside / "a.txt").write_text("x")
    assert m._check_file(str(inside / "a.txt")) is None


def test_traversal_resolves_outside_root(tmp_path, monkeypatch):
    inside = tmp_path / "ok"
    inside.mkdir()
    (tmp_path / "secret.txt").write_text("x")
    monkeypatch.setenv("AEGIS_ALLOWED_ROOTS", str(inside))
    assert "outside" in m._check_file(str(inside / ".." / "secret.txt"))


def test_size_cap(tmp_path, monkeypatch):
    f = tmp_path / "big.txt"
    f.write_bytes(b"x" * 2048)
    monkeypatch.setattr(m, "MAX_FILE_BYTES", 1024)
    assert "exceeds" in m._check_file(str(f))


def test_prior_works_dir_checked(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_ALLOWED_ROOTS", str(tmp_path / "ok"))
    assert "outside" in m._check_dir(str(tmp_path))


def test_unknown_venue_rejected():
    assert "Unknown venue" in m._check_venues("IEEE,--evil")
    assert m._check_venues("IEEE, acm") is None


def test_output_sanitized_and_truncated():
    out = m._sanitize_output("a\x1b[31mred\x1b[0m\x00" + "z" * (m.MAX_OUTPUT_CHARS + 10))
    assert "\x1b" not in out and "\x00" not in out
    assert "truncated" in out


def test_abs_path_never_option_like(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not m._abs("-x.pdf").startswith("-")


def test_safe_doi_neutralises_url_metacharacters():
    from aegis.detectors.citation import _safe_doi
    out = _safe_doi("10.1000/abc?x=1#f/../../etc")
    assert "?" not in out and "#" not in out and ".." not in out
