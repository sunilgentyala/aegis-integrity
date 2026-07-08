"""AEGIS Academic Integrity MCP Server — FastMCP edition.

Compatible with mcp >= 1.0.0. Uses FastMCP for zero-boilerplate stdio transport.
Run with: C:\Gitrepos\aegis-integrity\.venv\Scripts\python.exe aegis_mcp.py
"""

import os
import subprocess
import asyncio
from pathlib import Path
from mcp.server.fastmcp import FastMCP

AEGIS_EXE    = Path(r"C:\Gitrepos\aegis-integrity\.venv\Scripts\aegis.exe")
INDEX_DIR    = Path(r"C:\Gitrepos\aegis-integrity\aegis_index")
REPORT_DIR   = Path(r"C:\Gitrepos\aegis-integrity\aegis_reports")
DOTENV_PATH  = Path(r"C:\Gitrepos\aegis-integrity\.env")

# Load .env so AEGIS_CITATION_EMAIL etc. are available to subprocesses
if DOTENV_PATH.exists():
    for _line in DOTENV_PATH.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

mcp = FastMCP("aegis-integrity")


def _run(args: list[str], timeout: int = 300) -> str:
    """Run aegis CLI and return output."""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [str(AEGIS_EXE)] + args,
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as ex:
        partial = (ex.stdout or "").strip() if isinstance(ex.stdout, str) else ""
        msg = (
            f"AEGIS analysis timed out after {timeout}s and was terminated.\n"
            "This usually means the paper has a large reference list and citation "
            "verification against Crossref/OpenAlex is slow, or the AI-detection "
            "model is still downloading on first run.\n"
            "Try again with skip_citations=True or skip_ai_detection=True to "
            "isolate the slow stage, or re-run (models are cached after first use)."
        )
        if partial:
            msg += f"\n\nPartial output before timeout:\n{partial[-2000:]}"
        return msg
    out = result.stdout.strip()
    if result.returncode != 0 and result.stderr.strip():
        out = (out + "\nSTDERR:\n" + result.stderr.strip()).strip()
    return out or "(no output)"


@mcp.tool()
def aegis_analyze_paper(
    file_path: str,
    prior_works_dir: str = "",
    skip_ai_detection: bool = False,
    skip_citations: bool = False,
    html_report: bool = True,
) -> str:
    """Analyze an academic paper (PDF/DOCX/TEX/TXT) with AEGIS v2.0.

    Runs all 10 detection modules: n-gram and semantic plagiarism, ESL-calibrated
    AI content detection, Crossref citation hallucination verification, LLM watermark
    detection, stylometric ghostwriting profiling, self-plagiarism, semantic coherence.

    Use before any IEEE paper submission, or whenever asked about plagiarism,
    AI detection, citation integrity, or paper authenticity.

    Args:
        file_path: Absolute path to the paper file.
        prior_works_dir: Optional directory of your own prior papers for self-plagiarism.
        skip_ai_detection: Skip GPT-2 AI detection (faster). Default False.
        skip_citations: Skip Crossref citation lookup (offline mode). Default False.
        html_report: Also save a self-contained HTML report. Default True.
    """
    stem = Path(file_path).stem
    json_out = str(REPORT_DIR / f"{stem}_report.json")
    args = ["analyze", file_path, "--output", json_out, "--index-dir", str(INDEX_DIR)]

    if html_report:
        args += ["--html", str(REPORT_DIR / f"{stem}_report.html")]
    if prior_works_dir:
        args += ["--prior-works", prior_works_dir]
    if skip_ai_detection:
        args.append("--no-ai")
    if skip_citations:
        args.append("--no-citations")

    output = _run(args, timeout=600)
    if Path(json_out).exists():
        output += f"\n\nReport saved to: {json_out}"
    return output


@mcp.tool()
def aegis_compare_papers(file1: str, file2: str) -> str:
    """Compare two papers directly for similarity or self-plagiarism.

    Useful for checking a conference draft against a journal extension,
    or comparing two versions of the same paper.

    Args:
        file1: Absolute path to the first paper.
        file2: Absolute path to the second paper.
    """
    return _run(["compare", file1, file2], timeout=600)


@mcp.tool()
def aegis_check_citations(file_path: str) -> str:
    """Verify citation integrity in a paper (fast — citations module only).

    Checks each DOI via the Crossref REST API. Detects hallucinated DOIs,
    mismatched author/year/title, predatory journals, self-citation inflation,
    and high missing-DOI rate (AI fabrication signature).

    Args:
        file_path: Absolute path to the paper file.
    """
    stem = Path(file_path).stem
    json_out = str(REPORT_DIR / f"{stem}_citations.json")
    args = [
        "analyze", file_path,
        "--no-ai", "--no-semantic", "--no-stylometric", "--no-self-plagiarism",
        "--output", json_out,
    ]
    return _run(args, timeout=120)


@mcp.tool()
def aegis_index_summary() -> str:
    """Show what papers are in the AEGIS corpus index for plagiarism comparison."""
    return _run(["index", "summary", "--index-dir", str(INDEX_DIR)], timeout=30)


@mcp.tool()
def aegis_index_add(file_path: str, label: str = "") -> str:
    """Add a paper to the AEGIS corpus index for future plagiarism comparisons.

    Args:
        file_path: Absolute path to the paper file to index.
        label: Short label (e.g. 'Gentyala2025ARGUS'). Defaults to filename stem.
    """
    args = ["index", "add", file_path, "--index-dir", str(INDEX_DIR)]
    if label:
        args += ["--label", label]
    return _run(args, timeout=60)


if __name__ == "__main__":
    mcp.run()
