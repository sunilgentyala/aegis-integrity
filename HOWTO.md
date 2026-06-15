# AEGIS How-To Guide

Complete step-by-step instructions for installing, configuring, and using every feature of AEGIS.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [Command-Line Interface](#4-command-line-interface)
5. [Python API](#5-python-api)
6. [REST API](#6-rest-api)
7. [Understanding the Report](#7-understanding-the-report)
8. [Detector Reference](#8-detector-reference)
9. [Building a Corpus Index](#9-building-a-corpus-index)
10. [Self-Plagiarism Workflow](#10-self-plagiarism-workflow)
11. [Docker Deployment](#11-docker-deployment)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

| Requirement | Minimum version | Notes |
|-------------|-----------------|-------|
| Python | 3.9 | 3.11 recommended |
| pip | 22.0 | |
| RAM | 4 GB | 8 GB recommended with ML models |
| Disk | 1 GB | +1.5 GB if using gpt2-medium |
| Internet | Optional | Required for citation verification via Crossref |

---

## 2. Installation

### Option A -- Minimal (no ML, no SBERT, no GPT-2)

Runs the n-gram detector, citation verifier, stylometric analyzer, and self-plagiarism
detector using heuristics only. No large model downloads.

```bash
git clone https://github.com/sunilgentyala/aegis-integrity.git
cd aegis-integrity
pip install -e .
```

### Option B -- Full (all detectors)

Adds SBERT semantic search (80 MB model) and GPT-2 AI detection (500 MB model).

```bash
pip install -e ".[ml,nlp,bib]"
```

### Option C -- Docker (recommended for servers / shared use)

```bash
docker compose up --build
```

The container pre-downloads the SBERT model at build time so the first analysis
request is fast. Data persists in a Docker volume.

---

## 3. Configuration

Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
```

```ini
# .env
AEGIS_INDEX_DIR=./aegis_index       # where corpus index files are stored
AEGIS_REPORT_DIR=./aegis_reports    # where JSON/HTML reports are written
AEGIS_DEVICE=cpu                    # cpu | cuda | mps
AEGIS_CITATION_EMAIL=you@uni.edu    # required by Crossref polite-pool ToS
```

All four variables can also be passed as arguments on the command line.

---

## 4. Command-Line Interface

### 4.1 Install the `aegis` command

```bash
pip install -e .
aegis --version
```

If the `aegis` command is not found after install, use `python -m aegis` instead.

### 4.2 Analyze a single file

```bash
aegis analyze paper.pdf
```

This runs all detectors that do not require a corpus (stylometric, AI, citation).
Output is printed to the terminal. Risk levels: `LOW | MEDIUM | HIGH | CRITICAL`.

### 4.3 Save reports

```bash
aegis analyze paper.pdf \
    --output report.json \
    --html  report.html
```

`report.html` is self-contained -- no internet connection needed to open it.

### 4.4 Analyze against a reference corpus

```bash
# Provide one or more files or directories as corpus sources:
aegis analyze paper.pdf \
    --corpus ./known_papers/ \
    --html   report.html
```

AEGIS builds an in-memory n-gram + SBERT index from the corpus before running.
For repeated analyses against the same corpus, use a persistent index (Section 9).

### 4.5 Self-plagiarism check

```bash
aegis analyze paper.pdf \
    --prior-works ./my_previous_papers/ \
    --html report.html
```

`--prior-works` accepts files or directories (PDF, DOCX, TEX, TXT).

### 4.6 Combine corpus and prior-works

```bash
aegis analyze submission.pdf \
    --corpus      ./journal_database/ \
    --prior-works ./my_papers/ \
    --index-dir   ./aegis_index/ \
    --html        report.html
```

### 4.7 Disable individual detectors

```bash
aegis analyze paper.pdf \
    --no-ai              # skip GPT-2 AI detection (saves ~500 MB RAM)
    --no-citations       # skip Crossref lookup (useful offline)
    --no-semantic        # skip SBERT (saves ~80 MB RAM)
    --no-stylometric     # skip Burrows' Delta analysis
    --no-self-plagiarism # skip self-plagiarism check
```

### 4.8 Direct pairwise comparison

Compare two documents directly without a corpus -- useful for checking a conference
draft against a journal extension:

```bash
aegis compare conference_draft.pdf journal_submission.pdf
```

Add `--no-sbert` for a fast n-gram-only comparison:

```bash
aegis compare draft_v1.pdf draft_v2.pdf --no-sbert
```

### 4.9 Corpus management commands

```bash
# Build a persistent index from a directory of PDFs:
aegis index build ./corpus_pdfs/ --index-dir ./aegis_index/

# Add a single document to an existing index:
aegis index add new_paper.pdf --index-dir ./aegis_index/ --label "Jones2025"

# Add and immediately rebuild the index:
aegis index add new_paper.pdf --index-dir ./aegis_index/ --rebuild

# Show what is in the index:
aegis index summary --index-dir ./aegis_index/
```

### 4.10 Start the API server

```bash
aegis serve                          # http://127.0.0.1:8000
aegis serve --host 0.0.0.0 --port 8080
aegis serve --reload                 # development hot-reload
```

---

## 5. Python API

### 5.1 Minimal analysis (no corpus)

```python
from aegis.core.pipeline import AEGISPipeline, PipelineConfig

cfg = PipelineConfig(
    citation_email="you@university.edu",
    run_ai_detector=True,
    run_citation_check=True,
    run_semantic=False,          # no corpus loaded, skip SBERT
    run_self_plagiarism=False,   # no prior works, skip
)
pipeline = AEGISPipeline(config=cfg)
report = pipeline.analyze("submission.pdf")

print(report.overall_risk)       # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
print(report.flags)              # list[str] -- human-readable flag descriptions
print(report.ai_score)           # 0.0 - 1.0
print(report.citation_score)     # fraction of references flagged
```

### 5.2 Analysis with corpus and prior works

```python
from aegis.core.pipeline import AEGISPipeline, PipelineConfig

pipeline = AEGISPipeline(config=PipelineConfig())

# Load reference corpus (prior papers, known sources):
pipeline.load_corpus([
    ("Smith2023", open("smith2023.txt").read()),
    ("Jones2024", open("jones2024.txt").read()),
])

# Load author's own prior publications for self-plagiarism:
pipeline.load_prior_works([
    ("MyConf2022", open("my_conf_2022.txt").read()),
    ("MyJournal2023", open("my_journal_2023.txt").read()),
])

report = pipeline.analyze("new_submission.pdf")
```

### 5.3 Generate reports

```python
from aegis.report.generator import ReportGenerator

gen = ReportGenerator(output_dir="./reports/")

json_path = gen.generate_json(report)   # returns path to .json file
html_path = gen.generate_html(report)   # returns path to .html file

print(f"HTML report: {html_path}")
```

### 5.4 Use individual detectors directly

**N-gram detector:**
```python
from aegis.detectors.ngram import NGramDetector

det = NGramDetector(word_threshold=0.25, char_threshold=0.40)
det.build_index([("source_A", text_a), ("source_B", text_b)])
matches = det.find_matches(query_text)

for m in matches:
    print(m.source_label, m.jaccard_estimate, m.match_type)
```

**Semantic detector (requires sentence-transformers):**
```python
from aegis.detectors.semantic import SemanticDetector

det = SemanticDetector(cosine_threshold=0.82)
det.build_index([("paper_A", text_a)])
matches = det.find_matches(query_text, top_k=5)

for m in matches:
    print(m.source_label, m.cosine_score, m.is_paraphrase)
```

**Citation integrity detector:**
```python
from aegis.core.document import DocumentParser
from aegis.detectors.citation import CitationIntegrityDetector

doc = DocumentParser().parse("paper.pdf")
det = CitationIntegrityDetector(email="you@uni.edu")
verdicts = det.verify_references(doc.references)

for v in verdicts:
    print(v.cite_key, v.verdict, v.issues)

print(det.summary(verdicts))
```

**Stylometric analyzer:**
```python
from aegis.detectors.stylometric import StylometricAnalyzer

az = StylometricAnalyzer(segment_size_words=300, change_threshold=0.40)
result = az.analyze(text)

print(result.is_consistent)
print(result.consistency_score)
for cp in result.change_points:
    if cp.flagged:
        print(f"Segment {cp.segment_index}: delta={cp.delta_distance:.3f}")
        print(f"  Preview: {cp.text_preview[:80]}")
```

**Self-plagiarism detector:**
```python
from aegis.detectors.self_plagiarism import SelfPlagiarismDetector

det = SelfPlagiarismDetector(use_sbert=True)
det.load_prior_works([("conf2022", prior_text)])
result = det.check_submission(submission_text)

print(f"Overlap: {result.overall_overlap_pct:.1f}%")
print(f"Risk: {result.risk_level}")
print(result.cope_guidance)
```

**AI content detector (requires transformers + torch):**
```python
from aegis.detectors.ai_detector import AIContentDetector

det = AIContentDetector(ensemble_threshold=0.60)
result = det.detect(text)

print(result.document_verdict)          # HUMAN | UNCERTAIN | AI_LIKELY | AI_DETECTED
print(result.ai_fraction)               # fraction of paragraphs flagged

for para in result.paragraph_scores:
    print(para.verdict, para.ensemble_score, para.text[:80])
```

### 5.5 Load a pre-built persistent index

```python
from aegis.corpus.indexer import CorpusIndexer
from aegis.core.pipeline import AEGISPipeline, PipelineConfig

indexer = CorpusIndexer("./aegis_index/")
pipeline = AEGISPipeline(config=PipelineConfig())

pipeline._ngram = indexer.load_ngram_detector()
pipeline._semantic = indexer.load_semantic_detector()
pipeline._corpus_loaded = True

report = pipeline.analyze("submission.pdf")
```

---

## 6. REST API

Start the server: `aegis serve` (or `docker compose up`).

Interactive docs: `http://localhost:8000/docs`

### 6.1 Health check

```bash
curl http://localhost:8000/health
# {"status":"ok","index_dir":"./aegis_index"}
```

### 6.2 Analyze a file

```bash
curl -X POST http://localhost:8000/analyze \
     -F "file=@submission.pdf"
```

Get HTML instead of JSON:
```bash
curl -X POST "http://localhost:8000/analyze?format=html" \
     -F "file=@submission.pdf" \
     -o report.html
```

Disable specific detectors:
```bash
curl -X POST "http://localhost:8000/analyze?run_ai=false&run_citations=true" \
     -F "file=@submission.pdf"
```

### 6.3 Add documents to the corpus

```bash
curl -X POST http://localhost:8000/corpus/add \
     -F "file=@reference_paper.pdf" \
     -F "label=Smith2023"
```

### 6.4 Build the search index

Run this after adding all corpus documents:
```bash
curl -X POST http://localhost:8000/corpus/build
```

### 6.5 Pairwise self-plagiarism comparison

```bash
curl -X POST http://localhost:8000/compare \
     -F "file_a=@journal_draft.pdf" \
     -F "file_b=@conference_paper.pdf" \
     -F "label_a=journal_v1" \
     -F "label_b=conf2022"
```

### 6.6 Include prior works in /analyze

```bash
curl -X POST http://localhost:8000/analyze \
     -F "file=@submission.pdf" \
     -F 'prior_works=[["conf2022", "full text of prior paper..."]]'
```

---

## 7. Understanding the Report

### 7.1 Overall risk levels

| Risk | Meaning | Typical action |
|------|---------|----------------|
| `LOW` | No significant concerns | Proceed to submission |
| `MEDIUM` | Minor issues or borderline signals | Review flagged passages; may need disclosure |
| `HIGH` | Significant concerns in one or more detectors | Revise before submission; consult co-authors |
| `CRITICAL` | Hallucinated citations, extensive verbatim copying, or high AI score | Do not submit; major revision required |

### 7.2 Score fields

| Field | Range | Interpretation |
|-------|-------|----------------|
| `plagiarism_score` | 0 -- 1 | Combined n-gram + semantic signal. > 0.40 = HIGH |
| `ai_content` | 0 -- 1 | AI ensemble score. > 0.60 = AI_LIKELY |
| `citation_issue_rate` | 0 -- 1 | Fraction of references flagged. > 0.10 = MEDIUM |
| `style_inconsistency` | 0 -- 1 | 1 minus consistency score. > 0.30 = potential ghostwriting |
| `self_recycling_pct` | 0 -- 100 | Percent of submission sentences matched to prior works |

### 7.3 Citation verdicts

| Verdict | Meaning |
|---------|---------|
| `VALID` | DOI resolves; year, first author, and title match |
| `MISMATCH` | DOI resolves but one or more fields differ |
| `HALLUCINATED` | DOI returns HTTP 404 (paper does not exist) or confidence < 0.30 |
| `UNRESOLVABLE` | Network error, timeout, or Crossref API failure |
| `NO_DOI` | No DOI found; title-based lookup attempted |

### 7.4 AI detection verdicts

| Verdict | Meaning |
|---------|---------|
| `HUMAN` | Score < 50% of threshold |
| `UNCERTAIN` | Score 50-100% of threshold |
| `AI_LIKELY` | Score 100-125% of threshold |
| `AI_DETECTED` | Score > 125% of threshold |

### 7.5 Self-plagiarism risk levels (COPE thresholds)

| Risk | Overlap | COPE guidance |
|------|---------|---------------|
| `LOW` | < 5% | Normal; no action needed |
| `MEDIUM` | 5-15% | Cite prior work; consider cover letter note |
| `HIGH` | 15-30% | Explicit disclosure and citation required |
| `CRITICAL` | > 30% or verbatim > 5 passages | Do not submit; major rewriting required |

---

## 8. Detector Reference

### 8.1 N-Gram Detector (always runs; no ML)

- **Algorithm:** MinHash (128 permutations) + LSH banding
- **Indices:** word 3-gram (catches verbatim copy) + character 5-gram (catches obfuscation)
- **Threshold:** word Jaccard > 0.25 or char Jaccard > 0.40 to flag
- **Speed:** sub-millisecond per paragraph on million-document corpora (LSH pre-filter)

### 8.2 Semantic Detector (requires sentence-transformers)

- **Model:** `paraphrase-MiniLM-L6-v2` -- 80 MB, fast CPU inference
- **Index:** FAISS `IndexFlatIP` (cosine via L2-normalized embeddings)
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (optional; improves precision)
- **Threshold:** cosine >= 0.82 to flag as paraphrase
- **Gap filled:** catches concept-level paraphrase where no exact words are shared

### 8.3 AI Content Detector (requires transformers + torch)

- **Model:** GPT-2 (500 MB base; optional gpt2-medium 1.5 GB for cross-perplexity)
- **Signals:** perplexity, burstiness, cross-perplexity ratio, stylometric ensemble
- **ESL calibration:** threshold multiplied by 0.80-1.00 based on detected language
- **Granularity:** every paragraph scored independently
- **Gap filled:** ESL bias correction; paragraph-level scoring

### 8.4 Citation Integrity Detector (requires requests)

- **API:** Crossref REST (`https://api.crossref.org/works/{doi}`) -- free, no key
- **Checks:** DOI existence, year, title similarity (word Jaccard >= 0.65), first author
- **Fallback:** title-based lookup when no DOI is present
- **Rate limit:** 150 ms polite delay per request (Crossref ToS)
- **Gap filled:** only AEGIS verifies citations against a live database

### 8.5 Stylometric Analyzer (no ML; pure Python)

- **Feature vector:** 60 dimensions (10 scalar + 50 function-word frequencies)
- **Scalar features:** avg/std sentence length, TTR, hapax ratio, Yule's K, punctuation density,
  passive voice ratio, nominalization density, Flesch-Kincaid grade, hedge density
- **Distance metric:** Burrows' Delta (mean absolute difference of normalized vectors)
- **Threshold:** delta > 0.40 from document baseline flags a segment
- **Gap filled:** ghostwriting and multi-author section detection within a single document

### 8.6 Self-Plagiarism Detector (uses SBERT if installed)

- **Layer 1:** Character 5-gram Jaccard >= 0.35 (verbatim copy)
- **Layer 2:** Word 3-gram Jaccard >= 0.25 (near-verbatim)
- **Layer 3:** SBERT cosine >= 0.88 (paraphrase recycling across languages)
- **Modes:** corpus (prior works) or pairwise (two documents)
- **Gap filled:** self-plagiarism open to individual authors without ScholarOne access

---

## 9. Building a Corpus Index

For institutions or repeated analyses against the same large corpus, build a persistent
index once and reuse it across all future analyses.

### Step 1: Collect documents

```bash
ls ./my_corpus/
# 2021_smith.pdf  2022_jones.pdf  2023_zhang.pdf  ...
```

Supported formats: `.pdf`, `.docx`, `.tex`, `.txt`.

### Step 2: Build the index

```bash
aegis index build ./my_corpus/ \
    --index-dir ./aegis_index/ \
    --pattern   "*.pdf"
```

This writes six files to `./aegis_index/`:
- `corpus_meta.json` -- document registry
- `ngram_word.pkl`, `ngram_char.pkl` -- MinHash LSH objects
- `ngram_word_index.pkl`, `ngram_char_index.pkl` -- key to text mappings
- `semantic.faiss`, `semantic_texts.pkl` -- FAISS index and sentence list

### Step 3: Add new documents incrementally

```bash
aegis index add new_2025_paper.pdf \
    --index-dir ./aegis_index/ \
    --label     "Williams2025" \
    --rebuild                    # re-indexes after adding
```

### Step 4: Analyze using the pre-built index

```bash
aegis analyze submission.pdf \
    --index-dir ./aegis_index/ \
    --html      report.html
```

No rebuild needed unless new documents were added.

---

## 10. Self-Plagiarism Workflow

This workflow checks a new journal submission against a prior conference paper.

### Step 1: Gather prior works

Collect your own previously published papers as PDF, DOCX, or TXT.

### Step 2: Pairwise comparison (quickest)

```bash
aegis compare journal_draft.pdf conference_paper.pdf \
    --label-a "Journal v1" \
    --label-b "ICSE 2023 Paper"
```

Output shows overlap percentage, risk level, COPE guidance, and the top 10 matching passages.

### Step 3: Full analysis with prior works (recommended for journal submission)

```bash
aegis analyze journal_draft.pdf \
    --prior-works ./my_published_papers/ \
    --html report.html
```

### Step 4: Interpret results

- Overlap < 5%: Normal. No action needed.
- Overlap 5-15%: Add a sentence in the cover letter: "This work extends our earlier
  conference paper [CITE]. Section X reuses the experimental setup description from [CITE]."
- Overlap 15-30%: Required COPE disclosure. May need to rephrase methods boilerplate.
- Overlap > 30%: Do not submit. Contact journal editor to clarify scope of new contribution.

---

## 11. Docker Deployment

### Run locally

```bash
docker compose up --build
```

### Environment variables for Docker

```yaml
# docker-compose.yml -- environment section
environment:
  - AEGIS_DEVICE=cpu
  - AEGIS_CITATION_EMAIL=your@email.com
  - AEGIS_INDEX_DIR=/data/index
  - AEGIS_REPORT_DIR=/data/reports
```

### Persistent data

All corpus index files and reports are stored in the `aegis_data` Docker volume and
survive container restarts. To inspect or back up:

```bash
docker compose exec aegis ls /data/index/
docker cp aegis-integrity-aegis-1:/data/index ./backup_index/
```

### GPU acceleration

Change `AEGIS_DEVICE=cpu` to `AEGIS_DEVICE=cuda` and add the NVIDIA runtime:

```yaml
# docker-compose.yml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

---

## 12. Troubleshooting

### `ModuleNotFoundError: No module named 'sentence_transformers'`

```bash
pip install -e ".[ml]"
```

### `ModuleNotFoundError: No module named 'fitz'` (PyMuPDF)

```bash
pip install PyMuPDF
```

### Citation check returns `UNRESOLVABLE` for valid DOIs

- Check your internet connection -- Crossref requires outbound HTTPS
- The Crossref API occasionally returns 503 under heavy load; retry later
- Use `--no-citations` to skip if working offline

### AI detector returns `UNCERTAIN` for clearly human text

- The GPT-2 perplexity threshold (default 45.0) is conservative to minimize false positives
- Academic writing naturally has lower perplexity than casual text
- Adjust with `PipelineConfig(ai_perplexity_threshold=35.0)` if needed
- For ESL authors, the ESL multiplier automatically reduces the threshold

### Index build fails with `MemoryError`

- Reduce batch size by editing `SemanticDetector._build_sbert_index()` (change `batch_size=64` to `batch_size=16`)
- Or use CPU-only mode with a smaller model: set `EMBED_MODEL = "paraphrase-albert-small-v2"` in `semantic.py`

### `aegis` command not found after `pip install -e .`

```bash
python -m aegis --version
# or
python -m aegis.cli --version
```

Make sure the Python Scripts directory is on your PATH.

### Tests fail with `TypeError` on `ParsedDocument`

Always pass all required positional fields: `path`, `format`, `title`, `authors`,
`abstract`, `full_text`, `sections`, `references`. See `aegis/core/document.py:37`.

---

## Running the Test Suite

```bash
python -m pytest tests/ -v
# Expected: 38 passed in ~1s (no network or ML model downloads required)
```

Run with coverage:
```bash
pip install pytest-cov
python -m pytest tests/ -v --cov=aegis --cov-report=term-missing
```
