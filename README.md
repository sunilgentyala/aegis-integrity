# AEGIS Academic Integrity Checker

**Open-source, bias-aware academic integrity analysis.**
No data sent to third-party services. Runs entirely offline after first model download.

---

## What AEGIS Does -- and Why It Is Novel

Every major plagiarism tool (Turnitin, iThenticate, PlagScan) shares the same four gaps.
AEGIS is the first open-source tool that closes all four simultaneously:

| Gap | Existing tools | AEGIS |
|-----|---------------|-------|
| **1. Citation hallucination** | None verify citations | Crossref DOI resolution with 5-class verdict (VALID / MISMATCH / HALLUCINATED / UNRESOLVABLE / NO\_DOI) |
| **2. ESL/bias in AI detection** | 61.3% false-positive rate on non-native writers (Stanford 2023) | Per-language threshold calibration (15 languages) |
| **3. Semantic / paraphrase plagiarism** | BM25 / TF-IDF only | SBERT dense retrieval + CrossEncoder reranking |
| **4. Self-plagiarism (text recycling)** | Locked behind ScholarOne / Turnitin private index | Open corpus-mode and pairwise comparison with COPE guidance |

Additional features:
- **Stylometric authorship profiling** (Burrows' Delta): detects ghostwriting and multi-author sections within a single submission
- **Paragraph-level AI scoring** instead of one document-level verdict
- **MinHash LSH** (character 5-gram + word 3-gram dual index) for sub-linear candidate retrieval over large corpora
- **Fully explainable HTML reports** -- no black-box scores; every flag cites the source sentence and the metric that triggered it

---

## Architecture

```
submission (PDF / DOCX / TEX / TXT)
       |
       v
  DocumentParser          -- multi-format parser (PyMuPDF / python-docx / TexSoup)
       |
  ┌────┴──────────────────────────────────────────────────────────┐
  │                        AEGISPipeline                          │
  │                                                               │
  │  NGramDetector          word 3-gram + char 5-gram MinHash LSH │
  │  SemanticDetector       SBERT + FAISS + CrossEncoder reranker │
  │  AIContentDetector      GPT-2 perplexity + burstiness + ESL   │
  │  CitationIntegrityDetector  Crossref REST API                  │
  │  StylometricAnalyzer    Burrows' Delta; 60-dim feature vector  │
  │  SelfPlagiarismDetector n-gram + SBERT vs. prior works        │
  └────────────────────────────┬──────────────────────────────────┘
                               |
                          AnalysisReport
                         /             \
                  JSON report       HTML report
                                  (self-contained,
                                   offline-viewable)
```

---

## Installation

**Minimal (no ML models, no SBERT/GPT-2):**
```bash
pip install -e .
```

**Full (all detectors):**
```bash
pip install -e ".[ml,nlp,bib]"
```

**Docker (recommended for production):**
```bash
docker compose up --build
# API available at http://localhost:8000
# Swagger UI at http://localhost:8000/docs
```

---

## Quick Start

### Command-line

```bash
# Analyze a submission (no corpus -- stylometric + AI + citation only):
aegis analyze my_paper.pdf --output report.json --html report.html

# Analyze against a corpus of prior papers:
aegis analyze my_paper.pdf --corpus ./prior_papers/ --html report.html

# Check for self-plagiarism against own prior publications:
aegis analyze my_paper.pdf \
    --prior-works ./my_previous_papers/ \
    --html report.html

# Direct pairwise comparison (conference vs. journal version):
aegis compare conference_draft.pdf journal_submission.pdf

# Build a persistent index for a large corpus (only once):
aegis index build ./corpus_dir/ --index-dir ./aegis_index/
aegis analyze my_paper.pdf --index-dir ./aegis_index/ --html report.html

# Start the REST API server:
aegis serve --host 0.0.0.0 --port 8000
```

### Python API

```python
from aegis.core.pipeline import AEGISPipeline, PipelineConfig

cfg = PipelineConfig(citation_email="you@university.edu")
pipeline = AEGISPipeline(config=cfg)

# Load a reference corpus (optional)
pipeline.load_corpus([("Smith2023", open("smith2023.txt").read())])

# Load your own prior publications (optional)
pipeline.load_prior_works([("My2022Conf", open("my2022.txt").read())])

report = pipeline.analyze("submission.pdf")
print(report.overall_risk)       # LOW | MEDIUM | HIGH | CRITICAL
print(report.flags)              # list of human-readable flag strings

from aegis.report.generator import ReportGenerator
gen = ReportGenerator("./reports")
gen.generate_html(report)        # writes reports/aegis_report_submission.html
```

### REST API

```bash
# Upload a file for analysis:
curl -X POST http://localhost:8000/analyze \
     -F "file=@paper.pdf" \
     -F "format=json"

# Add a document to the comparison corpus:
curl -X POST http://localhost:8000/corpus/add \
     -F "file=@reference_paper.pdf" \
     -F "label=Smith2023"

# Build the search index after adding documents:
curl -X POST http://localhost:8000/corpus/build

# Pairwise self-plagiarism comparison:
curl -X POST http://localhost:8000/compare \
     -F "file_a=@journal_version.pdf" \
     -F "file_b=@conference_draft.pdf"
```

---

## Detectors in Detail

### 1. Citation Integrity (Novel -- no open-source equivalent)

Resolves every DOI via the Crossref REST API and compares claimed metadata
against the actual publication record.

Verdicts:
- `VALID` -- year, first author, and title all match (similarity > 0.65)
- `MISMATCH` -- one or more fields differ
- `HALLUCINATED` -- DOI returns HTTP 404 (does not exist), or confidence drops below 0.30
- `UNRESOLVABLE` -- network error or API timeout
- `NO_DOI` -- no DOI present; title-based lookup attempted

### 2. AI Content Detection (ESL-calibrated)

Four signals combined in a weighted ensemble:
- GPT-2 sliding-window perplexity (low PPL = AI-like)
- Burstiness: coefficient of variation of sentence lengths
- Cross-perplexity ratio (Binoculars-inspired; optional, requires gpt2-medium)
- Stylometric signals: sentence length uniformity, hedge phrase density, TTR, first-person absence

ESL calibration multipliers lower the detection threshold for non-native writers
(e.g., threshold x 0.80 for Chinese/Korean/Japanese authors) to reduce false positives.

### 3. Semantic Similarity (SBERT)

- Embedding model: `paraphrase-MiniLM-L6-v2` (80 MB, CPU-friendly)
- Index: FAISS `IndexFlatIP` (cosine via L2-normalized vectors)
- Reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2` for precision re-ranking
- Catches concept-level paraphrase where no exact words are shared

### 4. N-Gram Similarity (MinHash LSH)

Dual index: word 3-gram (catches verbatim copy and light paraphrase) and character
5-gram (catches obfuscation via typos or character substitution). 128 permutations
per MinHash; sub-linear query time over large corpora via LSH banding.

### 5. Stylometric Authorship Profiling (Burrows' Delta)

60-dimensional feature vector per text segment:
- 10 scalar features: avg/std sentence length, TTR, hapax ratio, Yule's K,
  punctuation density, passive voice ratio, nominalization density,
  Flesch-Kincaid grade, hedge density
- 50 function-word frequency dimensions

Segments with Burrows' Delta > 0.40 from the document baseline are flagged as
potential ghostwritten sections.

### 6. Self-Plagiarism / Text Recycling

Three-layer detection:
1. Character 5-gram Jaccard (verbatim copy)
2. Word 3-gram Jaccard (near-verbatim / light edit)
3. SBERT cosine >= 0.88 (paraphrase recycling across languages)

Risk levels and COPE guidance follow the Committee on Publication Ethics
text recycling guidelines (15% / 30% thresholds).

---

## Report Fields

```json
{
  "overall_risk": "MEDIUM",
  "scores": {
    "plagiarism": 0.12,
    "ai_content": 0.35,
    "citation_issue_rate": 0.0,
    "style_inconsistency": 0.08,
    "self_recycling_pct": 4.2
  },
  "flags": ["..."],
  "ngram_matches": [...],
  "semantic_matches": [...],
  "ai_detection": {...},
  "citation_integrity": [...],
  "stylometric": {...},
  "self_plagiarism": {...}
}
```

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

The test suite (42 tests across all detectors) runs without any network calls
or ML model downloads. AI/LLM detectors are tested via heuristic paths and mocks.

---

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Default | Description |
|----------|---------|-------------|
| `AEGIS_INDEX_DIR` | `./aegis_index` | Persistent FAISS + MinHash index directory |
| `AEGIS_REPORT_DIR` | `./aegis_reports` | Output directory for JSON/HTML reports |
| `AEGIS_DEVICE` | `cpu` | PyTorch device (`cpu`, `cuda`, `mps`) |
| `AEGIS_CITATION_EMAIL` | `aegis-check@example.com` | Email for Crossref polite-pool |

All settings can also be passed as `PipelineConfig` arguments in the Python API.

---

## License

MIT License. See LICENSE file.

---

## Author

Sunil Gentyala -- Independent Research, HCL America Inc., Dallas TX, USA
Contact: sunil.gentyala@ieee.org

---

## Comparison with Existing Tools

| Feature | Turnitin | iThenticate | CopyLeaks | AEGIS |
|---------|----------|-------------|-----------|-------|
| Open-source | No | No | No | **Yes** |
| Citation hallucination detection | No | No | No | **Yes** |
| ESL-calibrated AI detection | No | No | Limited | **Yes** |
| Paragraph-level AI scoring | No | No | Yes | **Yes** |
| Semantic / paraphrase detection | Partial | No | Partial | **Yes** |
| Self-plagiarism (open corpus) | ScholarOne only | Paid | No | **Yes** |
| Stylometric ghostwriting detection | No | No | No | **Yes** |
| Explainable per-sentence attribution | No | No | Partial | **Yes** |
| Offline / air-gapped operation | No | No | No | **Yes** |
| REST API + CLI | No | API (paid) | API (paid) | **Yes** |
