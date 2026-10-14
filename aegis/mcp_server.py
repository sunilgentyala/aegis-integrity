r"""AEGIS MCP server (stdio) for Claude Code, Claude Desktop and any MCP client.

Installed as the ``aegis-mcp`` console script:

    pip install "aegis-integrity[mcp] @ git+https://github.com/sunilgentyala/aegis-integrity"
    aegis-mcp

Configuration (environment variables, all optional):

    AEGIS_INDEX_DIR    corpus index directory   (default: ~/.aegis/index)
    AEGIS_REPORT_DIR   HTML report directory    (default: ~/.aegis/reports)
    AEGIS_ENV_FILE     .env file to load         (default: ~/.aegis/.env)
    AEGIS_ALLOWED_ROOTS  os.pathsep-separated folders the tools may read
                         (default: unrestricted, but only PDF/DOCX/TEX/TXT
                         files up to AEGIS_MAX_FILE_MB, default 50, are read)

Each tool runs the ``aegis`` CLI in a child process (``python -m aegis``)
rather than in-process, so a slow first-run model download or a crash in a
detector can never wedge the MCP stdio pipe.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from aegis.paths import aegis_home, default_index_dir, default_report_dir, load_env_file

# Never read ./.env here: the MCP client picks the working directory, which may
# be an untrusted folder. Only AEGIS_ENV_FILE or ~/.aegis/.env are honoured.
load_env_file(os.environ.get("AEGIS_ENV_FILE") or aegis_home() / ".env")

mcp = FastMCP("aegis-integrity")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".tex", ".txt"}
MAX_FILE_BYTES = int(os.environ.get("AEGIS_MAX_FILE_MB", "50")) * 1024 * 1024
MAX_OUTPUT_CHARS = 60_000
MAX_PRIOR_WORKS_ENTRIES = 10_000
VALID_VENUES = {"IEEE", "ACM", "BCS", "IET", "ISACA", "ELSEVIER", "ALL"}
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Tool annotations tell the client what each tool can do. Nothing here deletes
# or overwrites user data; aegis_index_add only appends to the local index.
_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                             idempotentHint=True, openWorldHint=False)
_READ_ONLY_NET = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                 idempotentHint=True, openWorldHint=True)
_WRITES_INDEX = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                idempotentHint=False, openWorldHint=False)


def _allowed_roots() -> list[Path]:
    raw = os.environ.get("AEGIS_ALLOWED_ROOTS", "")
    return [Path(r).expanduser().resolve() for r in raw.split(os.pathsep) if r.strip()]


def _in_allowed_roots(path: Path) -> bool:
    roots = _allowed_roots()
    return not roots or any(path.is_relative_to(r) for r in roots)


def _sanitize_output(text: str) -> str:
    """Strip ANSI/control characters and cap size before text reaches the model."""
    text = _CTRL_RE.sub("", _ANSI_RE.sub("", text))
    if len(text) > MAX_OUTPUT_CHARS:
        extra = len(text) - MAX_OUTPUT_CHARS
        text = text[:MAX_OUTPUT_CHARS] + f"\n...[truncated, {extra} more characters]"
    return text


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
            msg += f"\n\nPartial output before timeout:\n{_sanitize_output(partial[-2000:])}"
        return msg
    out = _sanitize_output((out or "").strip())
    if proc.returncode != 0:
        out = (out + f"\n(exit code {proc.returncode})").strip()
    return out or "(no output)"


def _with_report(output: str, html_out: str, wanted: bool) -> str:
    if wanted and Path(html_out).exists():
        output += f"\n\nReport saved to: {html_out}"
    return output


def _check_file(file_path: str) -> str | None:
    """Validate a model-supplied path before it is handed to the CLI."""
    try:
        p = Path(file_path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return "Invalid file path."
    if not p.is_file():
        return (f"File not found: {file_path}\n"
                "Pass the absolute path to a PDF, DOCX, TEX or TXT file.")
    if p.suffix.lower() not in ALLOWED_EXTENSIONS:
        return ("Unsupported file type. AEGIS reads only "
                + ", ".join(sorted(ALLOWED_EXTENSIONS)) + " files.")
    if not _in_allowed_roots(p):
        return "Path is outside the folders allowed by AEGIS_ALLOWED_ROOTS."
    if p.stat().st_size > MAX_FILE_BYTES:
        return f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit (AEGIS_MAX_FILE_MB)."
    return None


def _check_dir(dir_path: str) -> str | None:
    try:
        p = Path(dir_path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return "Invalid folder path."
    if not p.is_dir():
        return f"Folder not found: {dir_path}"
    if not _in_allowed_roots(p):
        return "Folder is outside the folders allowed by AEGIS_ALLOWED_ROOTS."
    for n, _ in enumerate(p.rglob("*")):
        if n > MAX_PRIOR_WORKS_ENTRIES:
            return "Folder contains too many entries."
    return None


def _abs(file_path: str) -> str:
    """Absolute, resolved path, so it can never be parsed as a CLI option."""
    return str(Path(file_path).expanduser().resolve())


def _check_venues(venues: str) -> str | None:
    bad = [v for v in venues.replace(" ", "").upper().split(",") if v and v not in VALID_VENUES]
    if bad:
        return f"Unknown venue(s): {', '.join(bad)}. Use IEEE, ACM, BCS, IET, ISACA, ELSEVIER or all."
    return None


@mcp.tool(annotations=_READ_ONLY_NET)
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
    if prior_works_dir and (err := _check_dir(prior_works_dir)):
        return err
    if check_guidelines and (err := _check_venues(check_guidelines)):
        return err
    html_out = str(_report_dir() / f"{Path(file_path).stem}_report.html")
    args = ["analyze", _abs(file_path), "--index-dir", str(_index_dir())]
    if html_report:
        args += ["--html", html_out]
    if prior_works_dir:
        args += ["--prior-works", _abs(prior_works_dir)]
    if skip_ai_detection:
        args.append("--no-ai")
    if skip_citations:
        args.append("--no-citations")
    if check_guidelines:
        args += ["--guidelines", check_guidelines]
    return _with_report(_run(args, timeout=900), html_out, html_report)


@mcp.tool(annotations=_READ_ONLY)
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
    return _run(["compare", _abs(file1), _abs(file2)], timeout=900)


@mcp.tool(annotations=_READ_ONLY_NET)
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
    args = ["analyze", _abs(file_path),
            "--no-ai", "--no-semantic", "--no-stylometric", "--no-self-plagiarism"]
    if html_report:
        args += ["--html", html_out]
    return _with_report(_run(args, timeout=300), html_out, html_report)


@mcp.tool(annotations=_READ_ONLY)
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
    if err := _check_venues(venues):
        return err
    html_out = str(_report_dir() / f"{Path(file_path).stem}_guidelines.html")
    args = ["guidelines", _abs(file_path), "--venues", venues]
    if html_report:
        args += ["--html", html_out]
    return _with_report(_run(args, timeout=120), html_out, html_report)


@mcp.tool(annotations=_READ_ONLY)
def aegis_index_summary() -> str:
    """List the papers in the local AEGIS comparison corpus."""
    return _run(["index", "summary", "--index-dir", str(_index_dir())], timeout=30)


@mcp.tool(annotations=_WRITES_INDEX)
def aegis_index_add(file_path: str, label: str = "") -> str:
    """Add a paper to the local comparison corpus for future plagiarism checks.

    Args:
        file_path: Absolute path to the paper file to index.
        label: Short label (e.g. 'Smith2025'). Defaults to the file name.
    """
    if err := _check_file(file_path):
        return err
    args = ["index", "add", _abs(file_path), "--index-dir", str(_index_dir())]
    if label:
        args += [f"--label={label[:100]}"]
    return _run(args, timeout=120)


@mcp.tool(annotations=_READ_ONLY_NET)
def aegis_status() -> str:
    """Show which AEGIS checks are ready, which are missing, and how to fix them.

    Call this first if a check is skipped or reports "unavailable".
    """
    return _run(["doctor", "--plain"], timeout=60)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
