"""
AEGIS command-line interface.

Usage examples:

    # Analyze a single submission (no corpus):
    aegis analyze paper.pdf

    # Analyze with a corpus directory and prior works:
    aegis analyze paper.pdf --corpus ./prior_papers/ --prior-works ./my_papers/

    # Build a persistent index from a folder of PDFs:
    aegis index build ./corpus_dir/ --index-dir ./aegis_index/

    # Add a single document to an existing index:
    aegis index add paper.pdf --index-dir ./aegis_index/ --label "Smith2023"

    # Show corpus contents:
    aegis index summary --index-dir ./aegis_index/

    # Direct pairwise comparison (self-plagiarism check):
    aegis compare journal_version.pdf conference_version.pdf

    # Start the REST API server:
    aegis serve --host 0.0.0.0 --port 8000
"""

from __future__ import annotations
import os
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

RISK_COLORS = {
    "LOW": "green",
    "MEDIUM": "yellow",
    "HIGH": "red",
    "CRITICAL": "bold red",
    "UNKNOWN": "dim",
}


@click.group()
@click.version_option("1.0.0", prog_name="aegis")
def cli():
    """AEGIS Academic Integrity Checker -- open-source, bias-aware plagiarism analysis."""


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("submission", type=click.Path(exists=True))
@click.option("--corpus", "-c", multiple=True, type=click.Path(exists=True),
              help="File or directory to include in comparison corpus. Repeatable.")
@click.option("--prior-works", "-p", multiple=True, type=click.Path(exists=True),
              help="Author's own prior publications for self-plagiarism check. Repeatable.")
@click.option("--index-dir", default=None, type=click.Path(),
              help="Persistent index directory (use pre-built index).")
@click.option("--output", "-o", default=None, type=click.Path(),
              help="Write JSON report to this path.")
@click.option("--html", "output_html", default=None, type=click.Path(),
              help="Write HTML report to this path.")
@click.option("--no-ai", is_flag=True, help="Skip AI content detection.")
@click.option("--no-citations", is_flag=True, help="Skip citation integrity check.")
@click.option("--no-semantic", is_flag=True, help="Skip SBERT semantic search.")
@click.option("--no-stylometric", is_flag=True, help="Skip stylometric analysis.")
@click.option("--no-self-plagiarism", is_flag=True, help="Skip self-plagiarism check.")
@click.option("--device", default="cpu", show_default=True,
              help="PyTorch device (cpu / cuda).")
@click.option("--email", default="aegis-check@example.com", show_default=True,
              help="Email for Crossref polite pool.")
def analyze(
    submission, corpus, prior_works, index_dir,
    output, output_html, no_ai, no_citations, no_semantic,
    no_stylometric, no_self_plagiarism, device, email,
):
    """Run the full AEGIS analysis on SUBMISSION (PDF, DOCX, TEX, or TXT)."""
    from aegis.core.pipeline import AEGISPipeline, PipelineConfig
    from aegis.core.document import DocumentParser
    from aegis.corpus.indexer import CorpusIndexer
    from aegis.report.generator import ReportGenerator

    cfg = PipelineConfig(
        device=device,
        citation_email=email,
        run_ai_detector=not no_ai,
        run_citation_check=not no_citations,
        run_semantic=not no_semantic,
        run_stylometric=not no_stylometric,
        run_self_plagiarism=not no_self_plagiarism,
    )
    pipeline = AEGISPipeline(config=cfg)

    # Load corpus
    corpus_docs = _collect_docs(corpus)
    if index_dir and Path(index_dir).exists():
        console.print(f"Loading pre-built index from [cyan]{index_dir}[/]...")
        indexer = CorpusIndexer(index_dir, device=device)
        try:
            pipeline._ngram = indexer.load_ngram_detector()
            pipeline._corpus_loaded = True
        except FileNotFoundError as e:
            console.print(f"[yellow]Warning:[/] {e}")
        try:
            pipeline._semantic = indexer.load_semantic_detector()
        except (FileNotFoundError, ImportError) as e:
            console.print(f"[yellow]Warning:[/] {e}")
    elif corpus_docs:
        console.print(f"Indexing {len(corpus_docs)} corpus document(s)...")
        pipeline.load_corpus(corpus_docs)

    # Load prior works
    prior_docs = _collect_docs(prior_works)
    if prior_docs:
        console.print(f"Loading {len(prior_docs)} prior work(s) for self-plagiarism check...")
        pipeline.load_prior_works(prior_docs)

    console.print(f"\nAnalyzing [bold]{submission}[/]...")
    report = pipeline.analyze(submission)

    # Print summary
    risk_color = RISK_COLORS.get(report.overall_risk, "white")
    console.print(Panel(
        f"[bold {risk_color}]Overall Risk: {report.overall_risk}[/bold {risk_color}]\n"
        f"Plagiarism score: {report.plagiarism_score:.2f}  |  "
        f"AI score: {report.ai_score:.2f}  |  "
        f"Citation issues: {report.citation_score:.0%}  |  "
        f"Self-recycling: {report.self_recycle_score*100:.1f}%\n"
        f"Analysis time: {report.elapsed_seconds}s",
        title="AEGIS Result",
    ))

    if report.flags:
        console.print("[bold]Flags:[/]")
        for flag in report.flags:
            console.print(f"  [yellow]•[/] {flag}")

    # Write outputs
    report_dir = str(Path(output).parent) if output else "."
    reporter = ReportGenerator(report_dir)

    if output:
        path = reporter.generate_json(report, Path(output).name)
        console.print(f"\nJSON report: [cyan]{path}[/]")

    if output_html:
        rdir = str(Path(output_html).parent)
        rep2 = ReportGenerator(rdir)
        path = rep2.generate_html(report, Path(output_html).name)
        console.print(f"HTML report: [cyan]{path}[/]")

    # Exit code reflects risk
    sys.exit(0 if report.overall_risk in ("LOW", "MEDIUM") else 1)


# ---------------------------------------------------------------------------
# compare (pairwise)
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("doc_a", type=click.Path(exists=True))
@click.argument("doc_b", type=click.Path(exists=True))
@click.option("--label-a", default=None)
@click.option("--label-b", default=None)
@click.option("--no-sbert", is_flag=True,
              help="Disable SBERT semantic matching (faster, n-gram only).")
def compare(doc_a, doc_b, label_a, label_b, no_sbert):
    """Direct pairwise self-plagiarism comparison between two documents."""
    from aegis.core.document import DocumentParser
    from aegis.detectors.self_plagiarism import SelfPlagiarismDetector

    label_a = label_a or Path(doc_a).stem
    label_b = label_b or Path(doc_b).stem

    parser = DocumentParser()
    console.print(f"Parsing [cyan]{doc_a}[/]...")
    text_a = parser.parse(doc_a).full_text
    console.print(f"Parsing [cyan]{doc_b}[/]...")
    text_b = parser.parse(doc_b).full_text

    detector = SelfPlagiarismDetector(use_sbert=not no_sbert)
    console.print("Comparing documents...")
    result = detector.compare_documents(text_a, label_a, text_b, label_b)

    risk_color = RISK_COLORS.get(result.risk_level, "white")
    console.print(Panel(
        f"Overlap: [bold]{result.overall_overlap_pct:.1f}%[/bold]  |  "
        f"Risk: [bold {risk_color}]{result.risk_level}[/bold {risk_color}]\n\n"
        f"{result.cope_guidance}",
        title=f"Self-Plagiarism: {label_a} vs {label_b}",
    ))

    if result.recycled_passages:
        t = Table("Type", "Char J", "Word J", "Submission excerpt",
                  "Prior work excerpt", box=box.SIMPLE)
        for p in result.recycled_passages[:10]:
            t.add_row(
                p.overlap_type,
                f"{p.char_jaccard:.3f}",
                f"{p.word_jaccard:.3f}",
                p.submission_text[:80],
                p.source_text[:80],
            )
        console.print(t)


# ---------------------------------------------------------------------------
# index subcommands
# ---------------------------------------------------------------------------

@cli.group()
def index():
    """Manage the persistent AEGIS corpus index."""


@index.command("build")
@click.argument("directory", type=click.Path(exists=True))
@click.option("--index-dir", default="./aegis_index", show_default=True)
@click.option("--pattern", default="*.pdf", show_default=True,
              help="File glob for documents to index.")
@click.option("--num-perm", default=128, show_default=True)
@click.option("--device", default="cpu", show_default=True)
def index_build(directory, index_dir, pattern, num_perm, device):
    """Build a new persistent index from all matching files in DIRECTORY."""
    from aegis.corpus.indexer import CorpusIndexer
    indexer = CorpusIndexer(index_dir, device=device)
    labels = indexer.add_directory(directory, pattern=pattern)
    console.print(f"Added {len(labels)} document(s).")
    console.print("Building indices...")
    indexer.build_indices(num_perm=num_perm)
    console.print(f"[green]Index built:[/] {index_dir}")


@index.command("add")
@click.argument("path", type=click.Path(exists=True))
@click.option("--index-dir", default="./aegis_index", show_default=True)
@click.option("--label", default=None)
@click.option("--rebuild", is_flag=True, help="Rebuild indices after adding.")
@click.option("--device", default="cpu", show_default=True)
def index_add(path, index_dir, label, rebuild, device):
    """Add a single document to the persistent index."""
    from aegis.corpus.indexer import CorpusIndexer
    indexer = CorpusIndexer(index_dir, device=device)
    assigned = indexer.add_document(path, label=label)
    console.print(f"Added as [cyan]{assigned}[/].")
    if rebuild:
        console.print("Rebuilding indices...")
        indexer.build_indices()
        console.print("[green]Done.[/]")
    else:
        console.print("[yellow]Run 'aegis index build' to update search indices.[/]")


@index.command("summary")
@click.option("--index-dir", default="./aegis_index", show_default=True)
def index_summary(index_dir):
    """List all documents in the persistent index."""
    from aegis.corpus.indexer import CorpusIndexer
    indexer = CorpusIndexer(index_dir)
    summary = indexer.corpus_summary()
    t = Table("Label", "Words", "Added", box=box.SIMPLE)
    for doc in summary["documents"]:
        t.add_row(doc["label"], str(doc["word_count"]), doc["added_at"][:10])
    console.print(t)
    console.print(f"Total: {summary['document_count']} document(s) in {index_dir}")


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True)
@click.option("--reload", is_flag=True, help="Enable hot-reload (development only).")
def serve(host, port, reload):
    """Start the AEGIS REST API server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn not installed:[/] pip install uvicorn[standard]")
        sys.exit(1)
    console.print(f"Starting AEGIS API on [cyan]http://{host}:{port}[/]")
    uvicorn.run(
        "aegis.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_docs(paths) -> list[tuple[str, str]]:
    """
    Given a sequence of file/directory paths, parse each and return
    (label, text) pairs. Directories are walked for PDF/DOCX/TEX files.
    """
    from aegis.core.document import DocumentParser
    parser = DocumentParser()
    docs = []
    exts = {".pdf", ".docx", ".tex", ".txt"}
    for path in paths:
        p = Path(path)
        candidates = (
            [p] if p.is_file() else
            [f for f in p.rglob("*") if f.suffix.lower() in exts]
        )
        for fp in candidates:
            try:
                parsed = parser.parse(str(fp))
                docs.append((fp.stem, parsed.full_text))
            except Exception as exc:
                console.print(f"[yellow]Warning:[/] Could not parse {fp}: {exc}")
    return docs


if __name__ == "__main__":
    cli()
