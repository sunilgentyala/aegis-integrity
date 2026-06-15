"""
AEGIS FastAPI REST interface.

Endpoints:
  POST /analyze           -- upload a file and run full analysis
  POST /corpus/add        -- add a document to the comparison corpus
  POST /corpus/build      -- (re)build all indices after adding documents
  GET  /corpus/summary    -- list indexed documents
  POST /compare           -- direct pairwise comparison (no corpus needed)
  GET  /health            -- liveness check

All file uploads are handled via multipart/form-data.
Results are returned as JSON (or HTML when ?format=html is appended).

Run with:
    uvicorn aegis.api.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations
import os
import tempfile
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from aegis.core.pipeline import AEGISPipeline, PipelineConfig
from aegis.corpus.indexer import CorpusIndexer
from aegis.report.generator import ReportGenerator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

INDEX_DIR = os.environ.get("AEGIS_INDEX_DIR", "./aegis_index")
REPORT_DIR = os.environ.get("AEGIS_REPORT_DIR", "./aegis_reports")
DEVICE = os.environ.get("AEGIS_DEVICE", "cpu")
CITATION_EMAIL = os.environ.get("AEGIS_CITATION_EMAIL", "aegis-check@example.com")

_indexer = CorpusIndexer(INDEX_DIR, device=DEVICE)
_pipeline: Optional[AEGISPipeline] = None
_reporter = ReportGenerator(REPORT_DIR)


def _get_pipeline() -> AEGISPipeline:
    global _pipeline
    if _pipeline is None:
        cfg = PipelineConfig(
            device=DEVICE,
            citation_email=CITATION_EMAIL,
        )
        _pipeline = AEGISPipeline(config=cfg)
    return _pipeline


app = FastAPI(
    title="AEGIS Academic Integrity Checker",
    description=(
        "Open-source plagiarism, AI content, citation integrity, "
        "stylometric, and self-plagiarism analysis for academic submissions."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok", "index_dir": INDEX_DIR}


@app.get("/corpus/summary")
def corpus_summary():
    return _indexer.corpus_summary()


@app.post("/corpus/add")
async def corpus_add(
    file: UploadFile = File(...),
    label: Optional[str] = Form(None),
):
    """
    Add a document to the comparison corpus.
    Call /corpus/build after adding all documents to update the search indices.
    """
    suffix = Path(file.filename).suffix if file.filename else ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        assigned_label = _indexer.add_document(tmp_path, label=label)
        return {"status": "added", "label": assigned_label}
    finally:
        os.unlink(tmp_path)


@app.post("/corpus/build")
def corpus_build(
    num_perm: int = Query(128, description="MinHash permutations"),
    word_threshold: float = Query(0.25),
    char_threshold: float = Query(0.40),
):
    """Rebuild all search indices from the current corpus."""
    _indexer.build_indices(
        num_perm=num_perm,
        word_threshold=word_threshold,
        char_threshold=char_threshold,
    )
    # Reload pipeline so it picks up the new indices
    global _pipeline
    _pipeline = None
    return {"status": "built", "summary": _indexer.corpus_summary()}


@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    format: str = Query("json", description="Output format: json | html"),
    run_ai: bool = Query(True),
    run_citations: bool = Query(True),
    run_semantic: bool = Query(True),
    run_stylometric: bool = Query(True),
    run_self_plagiarism: bool = Query(True),
    prior_works: Optional[str] = Form(
        None,
        description="JSON list of prior-work texts: [[label, text], ...]",
    ),
):
    """
    Run the full AEGIS analysis on an uploaded document.

    Returns JSON by default; use ?format=html for a browser-viewable report.
    """
    import json as _json

    suffix = Path(file.filename).suffix if file.filename else ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        cfg = PipelineConfig(
            device=DEVICE,
            citation_email=CITATION_EMAIL,
            run_ai_detector=run_ai,
            run_citation_check=run_citations,
            run_semantic=run_semantic,
            run_stylometric=run_stylometric,
            run_self_plagiarism=run_self_plagiarism,
        )
        pipeline = AEGISPipeline(config=cfg)

        # Load corpus from persisted indices if available
        try:
            ngram_det = _indexer.load_ngram_detector()
            pipeline._ngram = ngram_det
            pipeline._corpus_loaded = True
        except FileNotFoundError:
            pass  # No corpus indexed yet; proceed without

        try:
            sem_det = _indexer.load_semantic_detector()
            pipeline._semantic = sem_det
        except (FileNotFoundError, ImportError):
            pass

        # Load prior works if supplied
        if prior_works and pipeline._self_plag:
            try:
                works = _json.loads(prior_works)
                pipeline.load_prior_works(works)
            except Exception as exc:
                logger.warning("Could not parse prior_works: %s", exc)

        report = pipeline.analyze(tmp_path)

    finally:
        os.unlink(tmp_path)

    if format == "html":
        html_path = _reporter.generate_html(report)
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(content=f.read())

    return JSONResponse(_reporter._report_to_dict(report))


@app.post("/compare")
async def compare_pair(
    file_a: UploadFile = File(..., description="First document"),
    file_b: UploadFile = File(..., description="Second document (e.g. prior work)"),
    label_a: str = Form("document_a"),
    label_b: str = Form("document_b"),
):
    """
    Direct pairwise comparison: detects self-plagiarism between two documents
    without needing a pre-built corpus.
    """
    from aegis.detectors.self_plagiarism import SelfPlagiarismDetector
    from aegis.core.document import DocumentParser

    parser = DocumentParser()

    tmp_paths = []
    try:
        for upload_file in (file_a, file_b):
            suffix = Path(upload_file.filename).suffix if upload_file.filename else ".bin"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(await upload_file.read())
                tmp_paths.append(tmp.name)

        text_a = parser.parse(tmp_paths[0]).full_text
        text_b = parser.parse(tmp_paths[1]).full_text
    finally:
        for p in tmp_paths:
            if os.path.exists(p):
                os.unlink(p)

    detector = SelfPlagiarismDetector(use_sbert=False)
    result = detector.compare_documents(text_a, label_a, text_b, label_b)

    return {
        "label_a": label_a,
        "label_b": label_b,
        "overall_overlap_pct": result.overall_overlap_pct,
        "risk_level": result.risk_level,
        "cope_guidance": result.cope_guidance,
        "flags": result.flags,
        "top_passages": [
            {
                "type": p.overlap_type,
                "char_jaccard": p.char_jaccard,
                "word_jaccard": p.word_jaccard,
                "text_a": p.submission_text[:200],
                "text_b": p.source_text[:200],
            }
            for p in result.recycled_passages[:10]
        ],
    }
