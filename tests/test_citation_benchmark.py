"""Regression test for the synthetic citation benchmark.

Runs benchmarks/citations/run_eval.py (real parser + real citation detector,
simulated Crossref responses, no network) and checks that results still
match the committed results.json. If a change improves a known miss,
regenerate with `python benchmarks/citations/run_eval.py --write`.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "citations"


def _load_runner():
    spec = importlib.util.spec_from_file_location("aegis_citation_eval", BENCH / "run_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_benchmark_matches_committed_results():
    result = _load_runner().run()
    committed = json.loads((BENCH / "results.json").read_text(encoding="utf-8"))
    assert result["summary"]["references"] == committed["summary"]["references"]
    got = {r["ref"]: r["aegis_verdict"] for r in result["rows"]}
    want = {r["ref"]: r["aegis_verdict"] for r in committed["rows"]}
    assert got == want


def test_unverifiable_references_are_never_called_fabricated():
    s = _load_runner().run()["summary"]
    assert s["false_fabrication_claims"] == 0
    assert s["unverifiable_reported_as_problem"] == 0


def test_benchmark_makes_no_real_requests(monkeypatch):
    import socket

    def _no_socket(*a, **k):
        raise AssertionError("benchmark tried to open a real network connection")

    monkeypatch.setattr(socket, "create_connection", _no_socket)
    _load_runner().run()
