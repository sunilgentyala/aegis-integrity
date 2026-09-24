"""Readiness checks: which AEGIS checks can run on this machine, and how to fix the rest.

Used by ``aegis doctor``, the web UI's status panel (GET /status) and the
MCP ``aegis_status`` tool, so all three give the same answer.

Checks only look for installed packages and cached model files; nothing here
imports torch or downloads anything unless ``warm_up()`` is called.
"""

from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import aegis
from aegis.paths import aegis_home, default_index_dir

GIT_URL = "https://github.com/sunilgentyala/aegis-integrity"

READY, LIMITED, MISSING = "ready", "limited", "missing"


@dataclass
class Check:
    name: str          # plain-language name of the capability
    status: str        # ready | limited | missing
    detail: str        # what is (or isn't) available
    fix: str = ""      # one command or step that fixes it, if anything is needed


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def pip_hint(extra: str = "") -> str:
    """Install command for an optional extra, matching how AEGIS was installed."""
    suffix = f"[{extra}]" if extra else ""
    root = Path(aegis.__file__).resolve().parents[1]
    if (root / "setup.py").is_file():
        return f'pip install -e "{root}{suffix}"'
    return f'pip install "aegis-integrity{suffix} @ git+{GIT_URL}"'


def _hf_cached(repo_id: str, revision: str | None = None) -> bool | None:
    """True/False if we can tell whether a HuggingFace model is cached, None if we can't."""
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None
    try:
        hit = try_to_load_from_cache(repo_id, "config.json", revision=revision)
    except Exception:
        return None
    return isinstance(hit, str)


def _corpus_size(index_dir: Path) -> int | None:
    meta = index_dir / "corpus_meta.json"
    if not meta.is_file():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        for key in ("documents", "docs", "labels"):
            if isinstance(data.get(key), (list, dict)):
                return len(data[key])
    return len(data) if isinstance(data, (list, dict)) else None


def _crossref_reachable(timeout: float = 4.0) -> bool:
    try:
        import requests
        r = requests.head("https://api.crossref.org/works", timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False


def run_checks(offline: bool = False) -> list[Check]:
    checks: list[Check] = []

    core = [m for m in ("fitz", "docx", "TexSoup") if not _has(m)]
    checks.append(Check(
        "Read PDF, Word, LaTeX and text files",
        MISSING if core else READY,
        f"missing: {', '.join(core)}" if core else "PDF, DOCX, TEX, TXT supported",
        pip_hint() if core else "",
    ))

    index_dir = default_index_dir()
    n = _corpus_size(index_dir)
    if n:
        checks.append(Check("Plagiarism check against your own corpus", READY,
                            f"{n} document(s) indexed in {index_dir}"))
    else:
        checks.append(Check(
            "Plagiarism check against your own corpus", LIMITED,
            f"no corpus in {index_dir}; text-overlap checks have nothing to compare against",
            'aegis index build <folder of papers>   (or the "My comparison library" tab in `aegis ui`)',
        ))

    if _has("sentence_transformers") and _has("faiss"):
        cached = _hf_cached("sentence-transformers/paraphrase-MiniLM-L6-v2")
        checks.append(Check(
            "Paraphrase detection (meaning-level matches)", READY,
            "SBERT installed" + ("" if cached is not False else
                                 "; model (~80 MB) downloads on first use"),
            "" if cached is not False else "aegis doctor --warm-up",
        ))
    else:
        checks.append(Check("Paraphrase detection (meaning-level matches)", MISSING,
                            "sentence-transformers / faiss not installed", pip_hint("ml")))

    if _has("transformers") and _has("torch"):
        from aegis.detectors.ai_detector import AIContentDetector
        cached = _hf_cached(AIContentDetector.BASE_MODEL, AIContentDetector.BASE_MODEL_REVISION)
        checks.append(Check(
            "AI-written text detection", READY,
            "GPT-2 detector installed" + ("" if cached is not False else
                                          "; model (~550 MB) downloads on first use"),
            "" if cached is not False else "aegis doctor --warm-up",
        ))
    else:
        checks.append(Check("AI-written text detection", MISSING,
                            "transformers / torch not installed", pip_hint("ml")))

    checks.append(Check(
        "Fair scoring for non-native English writers",
        READY if _has("langdetect") else LIMITED,
        "language detected per document" if _has("langdetect")
        else "langdetect missing; every document is treated as English",
        "" if _has("langdetect") else pip_hint("ml"),
    ))

    if offline:
        checks.append(Check("Citation verification (Crossref)", LIMITED,
                            "not tested (offline mode)"))
    elif _crossref_reachable():
        email = os.environ.get("AEGIS_CITATION_EMAIL", "")
        if email and not email.endswith("@example.com"):
            checks.append(Check("Citation verification (Crossref)", READY,
                                "api.crossref.org reachable; only reference metadata is sent"))
        else:
            checks.append(Check(
                "Citation verification (Crossref)", LIMITED,
                "works, but without a contact email Crossref may slow or drop lookups "
                "(they show as 'timed out')",
                f"add AEGIS_CITATION_EMAIL=you@example.org to {aegis_home() / '.env'}",
            ))
    else:
        checks.append(Check(
            "Citation verification (Crossref)", LIMITED,
            "api.crossref.org not reachable; citation checks will report UNRESOLVABLE",
            "check your internet connection or proxy, or run with --no-citations",
        ))

    spacy_ok = _has("spacy") and _has("en_core_web_sm")
    checks.append(Check(
        "Grammar checks with full sentence parsing",
        READY if spacy_ok else LIMITED,
        "spaCy English model installed" if spacy_ok
        else "spaCy model not installed; grammar checks use simpler rules",
        "" if spacy_ok else f'{pip_hint("nlp")} && python -m spacy download en_core_web_sm',
    ))

    checks.append(Check(
        "Use from Claude / AI assistants (MCP)",
        READY if _has("mcp") else MISSING,
        "run `aegis-mcp`, or install the Claude plugin" if _has("mcp")
        else "MCP SDK not installed",
        "" if _has("mcp") else pip_hint("mcp"),
    ))
    return checks


def summary_line(checks: list[Check]) -> str:
    ready = sum(c.status == READY for c in checks)
    return f"{ready} of {len(checks)} capabilities ready"


def as_dicts(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]


def as_plain_text(checks: list[Check]) -> str:
    icon = {READY: "[OK]  ", LIMITED: "[WARN]", MISSING: "[MISS]"}
    lines = [f"AEGIS {aegis.__version__}: {summary_line(checks)}", ""]
    for c in checks:
        lines.append(f"{icon[c.status]} {c.name}: {c.detail}")
        if c.fix:
            lines.append(f"        fix: {c.fix}")
    return "\n".join(lines)


def warm_up(log=print) -> None:
    """Download and cache the ML models so the first real check is fast."""
    if _has("transformers") and _has("torch"):
        from aegis.detectors.ai_detector import AIContentDetector
        log("Downloading AI-detection model (GPT-2, ~550 MB)...")
        AIContentDetector()._load_models()
        log("  done")
    else:
        log(f"Skipping AI-detection model: install with {pip_hint('ml')}")
    if _has("sentence_transformers"):
        from aegis.detectors.semantic import SemanticDetector
        log("Downloading paraphrase models (SBERT + reranker, ~170 MB)...")
        SemanticDetector()._load_models()
        log("  done")
    else:
        log(f"Skipping paraphrase models: install with {pip_hint('ml')}")
