r"""AEGIS MCP server (stdio) for Claude Code, Claude Desktop and any MCP client.

Installed as the ``aegis-mcp`` console script:

    pip install "aegis-integrity[mcp] @ git+https://github.com/sunilgentyala/aegis-integrity"
    aegis-mcp

Configuration (environment variables, all optional):

    AEGIS_INDEX_DIR    corpus index directory   (default: ~/.aegis/index)
    AEGIS_REPORT_DIR   HTML report directory    (default: ~/.aegis/reports)
    AEGIS_ENV_FILE     .env file to load         (default: ~/.aegis/.env)

Each tool runs the ``aegis`` CLI in a child process (``python -m aegis``)
rather than in-process, so a slow first-run model download or a crash in a
detector can never wedge the MCP stdio pipe.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from aegis.paths import default_index_dir, default_report_dir, load_env_file

load_env_file()

mcp = FastMCP("aegis-integrity")


def _index_dir() -> Path:
    return default_index_dir()


def _report_dir() -> Path:
    return default_report_dir()


def _kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the child and anything it spawned (e.g. a model download)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()


def _run(args: list[str], timeout: int = 300) -> str:
    """Run the aegis CLI and return its output.

    - stdin=DEVNULL so the child can never block on (or consume) the MCP stdio pipe
    - the whole process tree is killed on timeout so a half-finished HuggingFace
      download cannot be orphaned holding cache locks
    - progress bars disabled; they flood the captured pipe during model downloads
    """
    _index_dir().mkdir(parents=True, exist_ok=True)
    _report_dir().mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    env.setdefault("TQDM_DISABLE", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    popen_kwargs = {}
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        [sys.executable, "-m", "aegis"] + args,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, text=True,
        encoding="utf-8", errors="replace", env=env, **popen_kwargs,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        partial = ""
        try:
            partial, _ = proc.communicate(timeout=10)
            partial = (partial or "").strip()
        except Exception:
            pass
        msg = (
            f"AEGIS timed out after {timeout}s and was stopped.\n"
            "The usual cause is the first-run model download (GPT-2 ~550MB + SBERT). "
            "Models are cached after one successful run, so re-running usually works. "
            "To download them outside this time limit, run once in a terminal:\n"
            "  aegis doctor --warm-up\n"
            "Setting HF_TOKEN in ~/.aegis/.env also speeds up downloads."
        )
        if partial:
            msg += f"\n\nPartial output before timeout:\n{partial[-2000:]}"
        return msg
    out = (out or "").strip()
    if proc.returncode != 0:
        out = (out + f"\n(exit code {proc.returncode})").strip()
    return out or "(no output)"


def _with_report(output: str, html_out: str, wanted: bool) -> str:
    if wanted and Path(html_out).exists():
        output += f"\n\nReport saved to: {html_out}"
    return output


def _check_file(file_path: str) -> str | None:
    if not Path(file_path).is_file():
        return (f"File not found: {file_path}\n"
                "Pass the absolute path to a PDF, DOCX, TEX or TXT file.")
    return None


@mcp.tool()
def aegis_analyze_paper(
    file_path: str,
    prior_works_dir: str = "",
    skip_ai_detection: bool = False,
    skip_citations: bool = False,
    check_guidelines: str = "",
    html_report: bool = True,
) -> str:
    """Run the full AEGIS integrity check on a paper (PDF/DOCX/TEX/TXT).

    Covers n-gram and semantic plagiarism against the local corpus, AI-content
    detection calibrated for non-native English writers, Crossref citation
    verification, LLM watermark heuristics, stylometric ghostwriting
    profiling, self-plagiarism, semantic coherence, venue verification,
    equation checks and grammar checks. Results support human review; they
    are not a finding of misconduct.

    Args:
        file_path: Absolute path to the paper file.
        prior_works_dir: Optional folder of the author's own earlier papers
            (for the self-plagiarism check).
        skip_ai_detection: Skip the GPT-2 based AI detector (faster, no model download).
        skip_citations: Skip Crossref lookups (fully offline).
        check_guidelines: Comma-separated subset of IEEE,ACM,BCS,IET,ISACA,ELSEVIER,
            or "all". Empty skips the guideline section.
        html_report: Save a self-contained HTML report. Default True.
    """
    if err := _check_file(file_path):
        return err
    html_out = str(_report_dir() / f"{Path(file_path).stem}_report.html")
    args = ["analyze", file_path, "--index-dir", str(_index_dir())]
    if html_report:
        args += ["--html", html_out]
    if prior_works_dir:
        args += ["--prior-works", prior_works_dir]
    if skip_ai_detection:
        args.append("--no-ai")
    if skip_citations:
        args.append("--no-citations")
    if check_guidelines:
        args += ["--guidelines", check_guidelines]
    return _with_report(_run(args, timeout=900), html_out, html_report)


@mcp.tool()
def aegis_compare_papers(file1: str, file2: str) -> str:
    """Compare two papers directly for overlap or self-plagiarism.

    Useful for a conference paper vs. its journal extension, or two versions
    of the same manuscript. Needs no corpus.

    Args:
        file1: Absolute path to the first paper.
        file2: Absolute path to the second paper.
    """
    for f in (file1, file2):
        if err := _check_file(f):
            return err
    return _run(["compare", file1, file2], timeout=900)


@mcp.tool()
def aegis_check_citations(file_path: str, html_report: bool = True) -> str:
    """Verify a paper's references against Crossref (citations module only).

    Flags hallucinated DOIs, author/year/title mismatches, predatory venues,
    self-citation inflation and a high missing-DOI rate. Only reference
    metadata is sent to Crossref; the paper text stays local.

    Args:
        file_path: Absolute path to the paper file.
        html_report: Save a self-contained HTML report. Default True.
    """
    if err := _check_file(file_path):
        return err
    html_out = str(_report_dir() / f"{Path(file_path).stem}_citations.html")
    args = ["analyze", file_path,
            "--no-ai", "--no-semantic", "--no-stylometric", "--no-self-plagiarism"]
    if html_report:
        args += ["--html", html_out]
    return _with_report(_run(args, timeout=300), html_out, html_report)


@mcp.tool()
def aegis_check_guidelines(file_path: str, venues: str = "all", html_report: bool = True) -> str:
    """Fast offline style pass: equations, grammar and per-publisher guidelines.

    Runs no ML models and makes no network calls, so it finishes in seconds.
    Each requested publisher is checked separately against its own guidance.

    Args:
        file_path: Absolute path to the paper file (PDF/DOCX/TEX/TXT).
        venues: Comma-separated subset of IEEE,ACM,BCS,IET,ISACA,ELSEVIER, or "all".
        html_report: Save a self-contained HTML report. Default True.
    """
    if err := _check_file(file_path):
        return err
    html_out = str(_report_dir() / f"{Path(file_path).stem}_guidelines.html")
    args = ["guidelines", file_path, "--venues", venues]
    if html_report:
        args += ["--html", html_out]
    return _with_report(_run(args, timeout=120), html_out, html_report)


@mcp.tool()
def aegis_index_summary() -> str:
    """List the papers in the local AEGIS comparison corpus."""
    return _run(["index", "summary", "--index-dir", str(_index_dir())], timeout=30)


@mcp.tool()
def aegis_index_add(file_path: str, label: str = "") -> str:
    """Add a paper to the local comparison corpus for future plagiarism checks.

    Args:
        file_path: Absolute path to the paper file to index.
        label: Short label (e.g. 'Smith2025'). Defaults to the file name.
    """
    if err := _check_file(file_path):
        return err
    args = ["index", "add", file_path, "--index-dir", str(_index_dir())]
    if label:
        args += ["--label", label]
    return _run(args, timeout=120)


@mcp.tool()
def aegis_status() -> str:
    """Show which AEGIS checks are ready, which are missing, and how to fix them.

    Call this first if a check is skipped or reports "unavailable".
    """
    return _run(["doctor", "--plain"], timeout=60)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
