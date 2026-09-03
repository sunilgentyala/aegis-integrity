# AEGIS Academic Integrity Checker

<p align="center">
  <img src="https://img.shields.io/badge/version-3.1.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-brightgreen?style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/offline-first-orange?style=for-the-badge" alt="Offline">
  <img src="https://img.shields.io/badge/bias--aware-ESL%20calibrated-purple?style=for-the-badge" alt="Bias Aware">
  <img src="https://img.shields.io/github/stars/sunilgentyala/aegis-integrity?style=for-the-badge" alt="Stars">
</p>

> **Open-source, offline, bias-aware academic integrity analysis.**
> Documents are processed entirely on your own hardware and never uploaded anywhere. Citation checks may query Crossref/OpenAlex with reference metadata (titles, authors, DOIs) when online verification is enabled.
> Analyzes plagiarism, AI-generated content, citation hallucinations, ghostwriting, predatory references, and essay mill patterns in a single pipeline -- plus an experimental token-distribution heuristic for LLM watermark research.
> **Plagiarism detection is corpus-based, not a live web/database crawl:** AEGIS compares your document against a corpus of papers *you supply* (your own prior works, a downloaded reference set, etc. -- see [Building a Corpus Index](HOWTO.md#9-building-a-corpus-index)). With no corpus loaded, plagiarism modules correctly report "no prior works loaded" rather than silently finding nothing to flag -- that isn't a scan failure.
> Results are a supporting signal for human review, not a determination of misconduct.

---

## How AEGIS Compares

Every major integrity tool has blind spots. AEGIS v3.1 aims to close **fourteen** of them simultaneously.

Based on each vendor's public documentation and pricing pages as of August 2026. "Not public" means the capability isn't documented publicly by that vendor -- not a confirmed absence. [Corrections welcome](https://github.com/sunilgentyala/aegis-integrity/issues).

| Gap | Turnitin | iThenticate | CopyLeaks | GPTZero | Originality.ai | **AEGIS v3.1** |
|-----|:--------:|:-----------:|:---------:|:-------:|:--------------:|:--------------:|
| Open-source / self-hostable | No | No | No | No | No | **Yes** |
| Citation hallucination detection | Not public | Not public | Not public | Not public | Not public | **Yes** |
| IEEE/ACM/Elsevier/IET/IETE/BCS -scoped venue-claim + duplicate-title check | Yes (full-text, paid Similarity Check membership) | Yes (full-text, paid Similarity Check membership) | Not public | Not public | Not public | **Yes (metadata-only via Crossref, free)** |
| LLM watermark token-distribution heuristic (experimental, keyless) | Not public | Not public | Not public | Not public | Not public | **Yes** |
| Citation network analysis (cartels, predatory) | Not public | Not public | Not public | Not public | Not public | **Yes** |
| ESL / non-native bias calibration (15 languages) | Not public | Not public | Not public | Not public | Not public | **Yes** |
| Paragraph-level AI scoring | Not public | Not public | Yes | Yes | Partial | **Yes** |
| Semantic / paraphrase plagiarism (SBERT) | Partial | Not public | Partial | Not public | Not public | **Yes** |
| Stylometric ghostwriting detection (Burrows' Delta) | Not public | Not public | Not public | Not public | Not public | **Yes** |
| Self-plagiarism against open corpus | Not public | Paid | Not public | Not public | Not public | **Yes** |
| Batch classroom / essay mill detection | Not public | Not public | Not public | Not public | Not public | **Yes** |
| Semantic coherence AI-polish detection | Not public | Not public | Not public | Not public | Not public | **Yes** |
| OpenAlex journal quality integration | Not public | Not public | Not public | Not public | Not public | **Yes** |
| Fully explainable per-sentence reports | Not public | Not public | Partial | Partial | Not public | **Yes** |
| Mathematical formula checking (equation numbering, dangling references, notation) | Not public | Not public | Not public | Not public | Not public | **Yes** |
| Grammar & language convention checking (contractions, US/UK spelling, agreement) | Not public | Not public | Not public | Not public | Not public | **Yes** |
| Per-venue publisher guideline compliance (IEEE/ACM/BCS/IET/ISACA/Elsevier, checked separately) | Not public | Not public | Not public | Not public | Not public | **Yes** |
| Offline / air-gapped operation | No | No | No | No | No | **Yes** |
| REST API + CLI (free) | No | Paid | Paid | Paid | Paid | **Yes** |
| Pricing model | Institutional (not public) | Institutional (not public) | Paid (self-serve) | Paid (self-serve) | Paid (self-serve) | **$0.00 (self-hosted)** |

---

## Fourteen Detection Modules

### 1. Citation Hallucination Detection
Resolves every DOI via the Crossref REST API and cross-checks author, year, and title.
A peer-reviewed study found ChatGPT fabricated up to 55% of references depending on model
version ([Walters & Wilder, *Scientific Reports*, 2023](https://doi.org/10.1038/s41598-023-41032-5)).

**Verdicts:** `VALID` | `MISMATCH` | `HALLUCINATED` | `UNRESOLVABLE` | `NO_DOI`

### 2. LLM Watermark Analysis -- Experimental (v2.1)
AEGIS ships two distinct capabilities here, and they should not be confused:

- **Experimental token-distribution anomaly heuristic** (default, `WatermarkMode.EXPERIMENTAL`):
  a keyless statistic loosely modeled on the shape of the Kirchenbauer (2023) green-list z-test
  and Zhao et al. (2023) entropy/rank-skew analysis. It does **not** have access to any real
  LLM provider's watermark key, seeding scheme, or tokenizer -- the "green list" it tests
  against is fabricated locally as a statistical null, not recovered from any actual
  deployment. It can report `STATISTICAL_ANOMALY` or `NO_STATISTICAL_ANOMALY`, never a
  definitive watermark claim, and it **never affects the overall integrity risk score**.
- **Known-scheme verification** (`WatermarkMode.VERIFIED_SCHEME`, opt-in): for when the real
  scheme, tokenizer, and key are actually known and supplied. AEGIS does not currently
  implement a real scheme's verifier, so this mode reports `UNSUPPORTED_CONFIGURATION`
  rather than silently falling back to the heuristic above.

See [Watermark Detection: Capabilities and Limitations](#watermark-detection-capabilities-and-limitations)
below before relying on any watermark output.

### 3. Citation Network Analysis (v2.0 -- novel)
Analyzes the full reference list for structural anomalies that single-citation DOI checking
misses:
- **Self-citation inflation** -- flags when >30% of references share an author with the submission
- **Predatory journal detection** -- heuristic pattern matching against known predatory name patterns
- **Citation clustering** -- detects when all references cluster in a single year (LLM fabrication signature)
- **OpenAlex integration** -- free API lookup for journal quality tier and citation impact
- **Missing DOI rate** -- very high DOI-absence is consistent with AI-hallucinated bibliographies

### 4. ESL-Calibrated AI Content Detection
Targets the bias documented by [Liang et al. (Stanford, 2023)](https://arxiv.org/abs/2304.02819):
GPT detectors misclassified more than half of non-native-authored TOEFL essays as AI-generated,
one detector flagging up to 98%, while native-English essays were scored accurately.
Applies per-language threshold multipliers for 15 languages. Paragraph-level scoring
pinpoints injected AI sections rather than giving one document-level verdict.

Signals: GPT-2 perplexity, burstiness, cross-perplexity ratio, stylometric ensemble,
GPT-4/GPT-5-era lexical-tell density (v2.5 -- transition/elevation vocabulary
disproportionately common in ChatGPT/GPT-4/GPT-5-family output, which GPT-2
perplexity alone under-detects against fluent frontier-model text).

### 5. Semantic Coherence Analysis (v2.0 -- novel)
Detects AI-polished text that passes perplexity filters because it was post-processed
by a humanizer. Targets the "too smooth to be human" signature:
- Discourse connector density (AI overuses "Furthermore", "Moreover", "Additionally")
- Sentence length uniformity (AI produces unnaturally low variance)
- Epistemic hedging rate (AI hedges at a formulaic, characteristic frequency)
- Section template matching (standard AI paper structure: Introduction -> Methods -> ...)

### 6. Semantic / Paraphrase Plagiarism
SBERT dense retrieval + CrossEncoder reranking catches concept-level paraphrase where
no exact words are shared. Traditional BM25/TF-IDF-only tools miss this entirely.

Model: `paraphrase-MiniLM-L6-v2` (80 MB, CPU-friendly). Index: FAISS `IndexFlatIP`.
Requires a corpus you load first (`--corpus`) -- there is no built-in web/database
crawl to compare against.

### 7. N-Gram Plagiarism (MinHash LSH)
Dual index: word 3-gram (verbatim copy) and character 5-gram (obfuscation via typos
or character substitution). 128 MinHash permutations; sub-linear query time over large
corpora via LSH banding. Also requires a loaded corpus -- same scope note as above.

### 8. Stylometric Authorship Profiling (Burrows' Delta)
60-dimensional feature vector per segment (10 scalar + 50 function-word dimensions).
Segments with Burrows' Delta > 0.40 from the document baseline are flagged as potential
ghostwritten sections. Catches professional essay mills that mix human and AI writing.

### 9. Self-Plagiarism / Text Recycling
Three-layer detection: character 5-gram Jaccard (verbatim), word 3-gram Jaccard
(near-verbatim), SBERT cosine >= 0.88 (cross-language paraphrase recycling).
Risk levels follow COPE text recycling guidelines (15% / 30% thresholds).

### 10. Batch / Classroom Analysis (v2.0 -- novel)
Detects essay mill operations and shared AI source documents by analyzing a set of
submissions simultaneously:
- Pairwise similarity matrix across all submissions (MinHash + rare vocabulary overlap)
- Structural fingerprinting (identical section sequences with different surface text)
- AI score clustering (statistically unlikely for a class to all independently write AI-like prose)
- Union-Find clustering to group submissions by suspected common source

### 11. Target-Publisher Verification (v2.4 -- novel)
Scopes citation and duplicate-submission checking to six publishers authors most
commonly ask about: **IEEE, ACM, Elsevier, IET, IETE, BCS**. No outside tool (this
one included) can query those publishers' actual full-text plagiarism databases --
Crossref's Similarity Check corpus that backs Turnitin/iThenticate is restricted to
paying member organizations, and Scopus/IEEE Xplore's public APIs are metadata- or
abstract-only even with a key. What this module does instead, entirely via free
Crossref metadata:
- **Venue-claim verification** -- flags a reference that reads as "IEEE Trans. ..."
  or "Proc. ACM ..." whose DOI actually resolves to a different publisher (venue
  misattribution or fabrication), reusing citations already resolved by module 1 --
  no extra network calls.
- **Duplicate-submission search** -- searches each target publisher (via Crossref
  member id for IEEE/ACM/Elsevier/IET; via DOI-prefix + container-title matching
  for IETE and BCS, which publish through Informa/Taylor & Francis and Oxford
  University Press respectively rather than holding their own Crossref membership)
  for near-identical titles already indexed under that venue.

Configurable via `--target-publishers IEEE,ACM,...` (CLI) or
`PipelineConfig.venue_target_publishers` (Python API); defaults to all six.

### 12. Mathematical Formula Checking (v3.0 -- novel)
Checks the structural integrity of numbered equations: consecutive numbering
(catches duplicates, gaps, and out-of-order numbers), dangling in-text references
to equation numbers that don't exist (a common leftover from renumbering during
revision), orphaned equations that are numbered but never referenced, and a set of
notation conventions sourced from actual publisher style manuals -- exponential
notation (`5E03` vs. `5×10³`), decimal leading zeros, percentage-range formatting,
and doubly-parenthesised references. Equations are extracted from LaTeX source
(`\begin{equation}`/`align`/`eqnarray`/...), from Word's native OMML math XML
(`python-docx` doesn't expose this at all -- `Paragraph.text` silently skips every
equation in a `.docx`), or via text-pattern heuristics for PDF/TXT. Pure Python,
no ML dependency. **This is a compliance/quality signal, not a misconduct signal --
it never affects `overall_risk`.**

### 13. Grammar & Language Convention Checking (v3.0 -- novel)
An offline, dependency-light grammar/usage checker: contraction detection
(`"don't"` in formal text), US/UK spelling-consistency detection across 30+ word
pairs, subject/verb agreement heuristics (`"the data is"` vs. `"the data are"`),
common usage errors (`"comprised of"`, `"could of"`, `"less samples"` vs. `"fewer
samples"`, decade/acronym apostrophe misuse), and readability metrics. Runs fully
in-process on regex + optional spaCy POS tagging (already an AEGIS dependency) --
no Java runtime, no external grammar service, no new hard dependency. Also a
compliance/quality signal, never part of `overall_risk`.

### 14. Per-Venue Publisher Guideline Compliance (v3.0 -- novel; Elsevier added v3.1)
Runs the math and grammar findings above against **six publishing bodies'
own sourced style guidance, checked SEPARATELY** rather than one generic merged
rule set -- so a document that's fine by ACM's conventions but violates an
IEEE-specific one (or vice versa) is visible per venue instead of averaged away:

| Venue | Sourced from | Distinguishing rule this catches |
|-------|--------------|-----------------------------------|
| **IEEE** | IEEE Editorial Style Manual for Authors (2024) | American spelling, no contractions, "(n)" equation citation, serial comma |
| **ACM** | ACM Formatting/Reference Guide (Chicago Manual of Style base) | American spelling, numeric-bracket citations, serial comma |
| **BCS** | *The Computer Journal* (OUP) General Instructions | No contraction/spelling rule published -- reported as inferred, not asserted |
| **IET** | IET Research Journals Author Guide | Bare `"(1)"` equation references (not `"Eq. (1)"`); scientific notation, not `5E03` |
| **ISACA** | ISACA Journal Article Submission Guidelines | **Third person required** ("avoid 'I' or 'you'"); 2,000-3,000 word target; endnotes, not numeric brackets |
| **Elsevier** | Elsevier Guide for Authors / CRediT / Highlights / Declaration of Competing Interest policy pages | **Either US or UK spelling accepted, just not mixed**; requires a CRediT authorship statement, a Declaration of Competing Interest, and a Data Availability Statement; Highlights capped at 3-5 bullets x 85 characters |

Results are `PASS` / `NEEDS_REVIEW` / `NOT_ENOUGH_DATA` -- advisory, never `FAIL`.
These are style conventions, not academic-integrity findings; AEGIS does not
claim to be a venue's editorial desk. Run via `aegis guidelines paper.pdf --venues
IEEE,ACM,BCS,IET,ISACA,ELSEVIER` (fast, no ML models at all) or opt in from `aegis
analyze ... --guidelines all`.

---

## Architecture

```
submission (PDF / DOCX / TEX / TXT)
       |
       v
  DocumentParser              -- PyMuPDF / python-docx / TexSoup / striprtf
       |
  ┌────┴──────────────────────────────────────────────────────────────┐
  │  AEGISPipeline v3.0                                               │
  │                                                                   │
  │  NGramDetector             word 3-gram + char 5-gram MinHash LSH  │
  │  SemanticDetector          SBERT + FAISS + CrossEncoder reranker  │
  │  AIContentDetector[v2.5]   GPT-2 perplexity+burstiness+ESL+tell   │
  │  CitationIntegrityDetector Crossref REST API (DOI resolution)     │
  │  StylometricAnalyzer       Burrows' Delta; 60-dim feature vector  │
  │  SelfPlagiarismDetector    SBERT + n-gram vs. prior works         │
  │  LLMWatermarkDetector [v2.1] experimental, no real key            │
  │  CitationNetworkAnalyzer[v2] self-cite inflation; OpenAlex        │
  │  SemanticCoherenceAnalyzer[v2] discourse connectors; uniformity   │
  │  BatchAnalyzer         [v2] classroom-level essay mill detection  │
  │  TargetPublisherVerifier[v2.4] IEEE/ACM/Elsevier/IET/IETE/BCS     │
  │  MathFormulaChecker    [v3.0] equation numbering/refs/notation    │
  │  GrammarLanguageChecker[v3.0] contractions/spelling/agreement     │
  │  GuidelineComplianceChecker[v3.0] IEEE/ACM/BCS/IET/ISACA/Elsevier │
  └────────────────────────────┬──────────────────────────────────────┘
                               |
                          AnalysisReport
                         /             \
                  JSON report       HTML report
                                  (self-contained,
                                   offline-viewable)
```

---

## Installation

**Minimal (no ML models -- citation, stylometric, watermark, coherence, math,
grammar, and per-venue guideline compliance; all pure-Python):**
```bash
pip install -e .
```

**Full (all 14 detectors):**
```bash
pip install -e ".[ml,nlp,bib]"
python -m spacy download en_core_web_sm
```

**Docker (recommended for production / air-gapped environments):**
```bash
docker compose up --build
# API available at http://localhost:8000 (bound to localhost only by default)
# Swagger UI at http://localhost:8000/docs
```
The container runs as a non-root user and its healthcheck needs no extra
tools. By default the compose file only publishes the API on the host's
loopback interface. Before exposing it beyond localhost (a different host
binding, a reverse proxy, etc.), set `AEGIS_API_KEY` -- otherwise every
route except `/health` is unauthenticated.

**Windows one-click:**
```bat
install.bat
```

---

## Quick Start

### Command-line

```bash
# Full analysis (all 14 detectors):
aegis analyze paper.pdf --output report.json --html report.html

# Fast, offline-only scan: math + grammar + per-venue guideline compliance,
# checked SEPARATELY for each requested venue -- no ML models at all:
aegis guidelines paper.pdf --venues IEEE,ACM,BCS,IET,ISACA,ELSEVIER --html guidelines.html

# Fold guideline compliance into the full analysis instead:
aegis analyze paper.pdf --guidelines all --html report.html

# Disable the experimental watermark heuristic entirely:
aegis analyze paper.pdf --watermark-mode disabled

# Against a reference corpus:
aegis analyze paper.pdf --corpus ./prior_papers/ --html report.html

# Self-plagiarism check against own prior publications:
aegis analyze paper.pdf --prior-works ./my_previous_papers/ --html report.html

# Pairwise comparison (conference vs. journal version):
aegis compare conference_draft.pdf journal_submission.pdf

# Batch / classroom analysis (essay mill detection):
aegis batch ./submissions/ --html batch_report.html

# Build a persistent index for a large corpus:
aegis index build ./corpus_dir/ --index-dir ./aegis_index/
aegis analyze paper.pdf --index-dir ./aegis_index/ --html report.html

# Start the REST API server:
aegis serve --host 0.0.0.0 --port 8000
```

### Python API

```python
from aegis.core.pipeline import AEGISPipeline, PipelineConfig

from aegis.detectors.watermark_detector import WatermarkMode

cfg = PipelineConfig(
    citation_email="you@university.edu",
    run_watermark_detector=True,       # v2.0
    watermark_mode=WatermarkMode.EXPERIMENTAL,  # default; never affects overall_risk
    run_citation_network=True,         # v2.0
    run_coherence_analyzer=True,       # v2.0
)
pipeline = AEGISPipeline(config=cfg)

# Load a reference corpus (optional)
pipeline.load_corpus([("Smith2023", open("smith2023.txt").read())])

# Load your own prior publications (optional)
pipeline.load_prior_works([("My2022Conf", open("my2022.txt").read())])

report = pipeline.analyze("submission.pdf")
print(report.overall_risk)           # LOW | MEDIUM | HIGH | CRITICAL

# v2.0 new fields
print(report.watermark_result)       # WatermarkResult
print(report.citation_network_result)# CitationNetworkResult
print(report.coherence_result)       # CoherenceResult

# v3.0 new fields -- compliance/quality signals, never part of overall_risk
print(report.math_result)            # MathAnalysisResult
print(report.grammar_result)         # GrammarAnalysisResult
print(report.guideline_results)      # {"IEEE": GuidelineComplianceResult, ...}
                                      # (empty unless PipelineConfig.guideline_venues is set)

from aegis.report.generator import ReportGenerator
gen = ReportGenerator("./reports")
gen.generate_html(report)

# Batch classroom analysis (v2.0)
from aegis.detectors.batch_analyzer import BatchAnalyzer
analyzer = BatchAnalyzer()
batch = analyzer.analyze(
    doc_names=["alice.pdf", "bob.pdf", "carol.pdf"],
    doc_texts=[text_alice, text_bob, text_carol],
    ai_scores=[0.72, 0.69, 0.71],
)
print(batch.overall_risk)            # CRITICAL if essay mill detected
print(batch.suspicious_pairs)
```

### REST API

```bash
# Upload for analysis:
curl -X POST http://localhost:8000/analyze \
     -F "file=@paper.pdf" -F "format=json"

# Add to reference corpus:
curl -X POST http://localhost:8000/corpus/add \
     -F "file=@reference.pdf" -F "label=Smith2023"

# Build search index:
curl -X POST http://localhost:8000/corpus/build

# Pairwise comparison:
curl -X POST http://localhost:8000/compare \
     -F "file_a=@journal.pdf" -F "file_b=@conference.pdf"

# Batch classroom analysis:
curl -X POST http://localhost:8000/batch \
     -F "files=@a.pdf" -F "files=@b.pdf" -F "files=@c.pdf"
```

---

## Report Fields (v2.1)

`detector_status` distinguishes "this detector found nothing" from "this detector
didn't run" -- a 0.0 score alone is ambiguous between a disabled detector, a
missing corpus, and a genuinely clean result. `citation_summary.assessment` is
`"INCONCLUSIVE"` (rather than a confident risk level) when fewer than 5
references were detected or verification coverage is below 80% -- a single
low-confidence reference should never read as "100% of citations are fabricated."

```json
{
  "overall_risk": "HIGH",
  "scores": {
    "plagiarism": 0.12,
    "ai_content": 0.71,
    "citation_issue_rate": 0.22,
    "style_inconsistency": 0.08,
    "self_recycling_pct": 4.2
  },
  "flags": ["AI content detected: AI_LIKELY (score=0.71)", "..."],
  "network_activity": {
    "document_content_transmitted": false,
    "citation_check_mode": "online",
    "citation_network_mode": "online",
    "external_services_contacted": ["Crossref", "OpenAlex"]
  },
  "detector_status": {
    "ngram": {"status": "completed", "reason": null},
    "semantic": {"status": "disabled", "reason": null},
    "ai_content": {"status": "completed", "reason": null},
    "citation": {"status": "completed", "reason": null},
    "self_plagiarism": {"status": "unavailable", "reason": "no prior works loaded"},
    "...": "one entry per detector -- completed | disabled | unavailable | failed"
  },
  "ai_detection": {
    "document_verdict": "AI_LIKELY",
    "ai_fraction": 0.62,
    "paragraph_scores": [...]
  },
  "citation_summary": {
    "total_references": 22,
    "references_with_identifier": 20,
    "references_verified": 19,
    "verification_coverage": 0.864,
    "assessment": "ASSESSED",
    "risk_level": "MEDIUM"
  },
  "citation_integrity": [...],
  "citation_network": {
    "self_citation_rate": 0.08,
    "predatory_journal_count": 0,
    "missing_doi_rate": 0.14,
    "flags": []
  },
  "watermark": {
    "mode": "experimental",
    "status": "completed",
    "verdict": "NO_STATISTICAL_ANOMALY",
    "evidence_status": "experimental",
    "affects_overall_risk": false,
    "tokens_evaluated": 842,
    "z_score": 0.41,
    "confidence": 0.0,
    "limitations": ["This is a keyless heuristic...", "..."]
  },
  "coherence": {
    "verdict": "AI_POLISHED",
    "ensemble_score": 0.63,
    "discourse_connector_density": 5.2,
    "sentence_length_cv": 0.29
  },
  "stylometric": {...},
  "self_plagiarism": {...}
}
```

---

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Default | Description |
|----------|---------|-------------|
| `AEGIS_INDEX_DIR` | `./aegis_index` | Persistent FAISS + MinHash index directory |
| `AEGIS_REPORT_DIR` | `./aegis_reports` | Output directory for JSON/HTML reports |
| `AEGIS_DEVICE` | `cpu` | PyTorch device (`cpu`, `cuda`, `mps`) |
| `AEGIS_CITATION_EMAIL` | `aegis-check@example.com` | Email for Crossref polite-pool |
| `AEGIS_API_KEY` | unset | If set, the REST API requires a matching `X-API-Key` header on every route except `/health`. Unset means no authentication -- only expose the API to a trusted network in that case. |
| `AEGIS_MAX_UPLOAD_MB` | `50` | Maximum upload size (MB) accepted by `/analyze`, `/compare`, and `/corpus/add`; larger uploads get HTTP 413. |
| `AEGIS_MAX_CONCURRENT_JOBS` | `2` | Maximum concurrent `/analyze` requests; additional requests get HTTP 503 instead of queuing. |

All settings can also be passed as `PipelineConfig` arguments in the Python API.

---

## Watermark Detection: Capabilities and Limitations

AEGIS's watermark analysis is **experimental by default and does not affect the overall
integrity risk score**. Before relying on any watermark output, understand:

- **An unrelated green list cannot verify a secret watermark.** Real watermark schemes
  (Kirchenbauer et al. 2023, etc.) partition the vocabulary using a secret key and a
  seeding scheme tied to the actual generating model's tokenizer. AEGIS's experimental
  heuristic has none of that -- it fabricates its own green/red split from a hash of the
  previous word, purely as a statistical null to compare against. Matching that fabricated
  null is not evidence of matching a real provider's watermark.
- **Tokenizer alignment matters.** The heuristic approximates tokens via a word-level hash,
  not the BPE tokenizer any real LLM actually uses. Token boundaries differ, which further
  breaks any correspondence to a real scheme.
- **Anomaly detection is not scheme verification.** A `STATISTICAL_ANOMALY` verdict means
  the heuristic's own null was exceeded -- it does not mean a watermark was found. Only a
  `VERIFIED_SCHEME` run against a real, correctly configured scheme (not currently
  implemented in AEGIS) could support that claim.
- **Minimum text length.** Fewer than 200 alphabetic tokens returns `INSUFFICIENT_TEXT` --
  short excerpts are not evaluated at all.
- **Paraphrasing and editing reduce detectability** of any real watermark, and AEGIS makes
  no claim about robustness to either.
- **Results require human interpretation.** Even a validated scheme signal (when/if
  implemented) is provenance evidence, not proof of misconduct, and is capped to raising
  risk by at most one level rather than forcing `CRITICAL`.
- **No provider-specific claims.** AEGIS does not claim to detect GPT-4, Gemini, Claude, or
  any other proprietary provider's watermark. No such scheme is documented or implemented
  here.

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

The test suite runs without network calls or ML model downloads.

---

## Why Choose AEGIS

**1. Local-first processing.** AEGIS never uploads your manuscript anywhere -- analysis
runs entirely on your own machine. Citation checks may query Crossref/OpenAlex with
reference metadata (titles, authors, DOIs), never the document itself, and only when
online verification is enabled.

**2. Reduced false-positive bias against international researchers.** [Liang et al. (Stanford,
2023)](https://arxiv.org/abs/2304.02819) found GPT detectors misclassified more than half of
non-native-authored TOEFL essays as AI-generated. AEGIS applies per-language calibration
across 15 languages to reduce this bias.

**3. Closes gaps not publicly documented elsewhere.** Citation cartels, essay mills, and
AI-polished text that passes perplexity filters are not publicly documented as covered by
mainstream tools. AEGIS also includes an experimental, informational-only LLM watermark
heuristic not commonly found in open-source alternatives -- see its
[capabilities and limitations](#watermark-detection-capabilities-and-limitations).

**4. Explainable, not a black box.** Every flag cites the exact sentence, the source it
was matched against, and the metric that triggered it, so a human reviewer can verify or
dismiss it -- rather than a single opaque score. AEGIS results are a supporting signal for
human review, not a determination of misconduct.

**5. Built for research institutions.** REST API for LMS integration, Docker for
air-gapped deployment, batch mode for classroom scanning, persistent indices for
journal editorial systems.

**6. Free, forever.** MIT license. No per-submission fees, no seat licenses, no vendor
lock-in -- commercial tools require an institutional license or paid API credits. AEGIS
costs compute time only.

---

## References

- Kirchenbauer et al. (2023). *A Watermark for Large Language Models.* ICML 2023.
- Zhao et al. (2023). *Provable Robust Watermarking for AI-Generated Text.* ICLR 2024.
- Liang et al. (2023). *GPT Detectors Are Biased Against Non-Native English Writers.* Patterns 4(7), 2023. [arXiv:2304.02819](https://arxiv.org/abs/2304.02819).
- Walters & Wilder (2023). *Fabrication and Errors in the Bibliographic Citations Generated by ChatGPT.* Scientific Reports 13, 14045. [doi:10.1038/s41598-023-41032-5](https://doi.org/10.1038/s41598-023-41032-5).
- Burrows (1987). *Word Patterns and Story Shapes.* Literary Linguistic Computing 2(2).
- McCarthy & Jarvis (2010). *MTLD, vocd-D, and HD-D.* Behavior Research Methods 42(2).
- COPE (2019). *Text Recycling Guidelines.* Committee on Publication Ethics.

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Author

**Sunil Gentyala**
Independent Research | HCL America Inc., Dallas TX, USA

| Credential | Detail |
|---|---|
| IEEE Senior Member | Institute of Electrical and Electronics Engineers |
| CISM | Certified Information Security Manager (ISACA) |
| ISACA | Information Systems Audit and Control Association |

Contact: sunil.gentyala@ieee.org
GitHub: [sunilgentyala](https://github.com/sunilgentyala)
LinkedIn: [linkedin.com/in/sunilgentyala](https://www.linkedin.com/in/sunilgentyala)
Website: [sunilgentyala.github.io/aegis-integrity](https://sunilgentyala.github.io/aegis-integrity)

---

## Changelog

### v3.1.0 (September 2026)
- **NEW:** Elsevier added as a sixth per-venue guideline profile
  (`aegis.guidelines.profiles.GUIDELINE_PROFILES["ELSEVIER"]`), sourced from
  Elsevier's own Guide for Authors / CRediT / Highlights / Declaration of
  Competing Interest policy pages and cross-checked against a real
  published ScienceDirect article. Unlike the other five venues, Elsevier
  explicitly accepts **either** US or UK spelling and only flags a document
  that mixes the two -- the checker's spelling rule was extended with a new
  `"EITHER"` variant to represent this correctly instead of forcing a false
  single-target verdict. Four new structural checks run only for venues
  that require them (Elsevier, for now): a CRediT authorship contribution
  statement, a Declaration of Competing Interest, a Data Availability
  Statement, and a Highlights section capped at 3-5 bullets of 85
  characters each.
- **SECURITY:** Fixed a timing side-channel in the REST API's
  `X-API-Key` check (`aegis.api.app.require_api_key`) -- it compared the
  header to `AEGIS_API_KEY` with plain `!=`, which short-circuits on the
  first mismatching character and so takes measurably longer to reject a
  key that matches more leading characters, in principle letting an
  attacker recover the key one character at a time. Now uses
  `hmac.compare_digest`.
- **SECURITY:** Raised minimum dependency versions past several since-
  disclosed CVEs: `transformers` (RCE via unsafe deserialization,
  CVE-2024-11394/11392), `torch` (`torch.load` RCE even with
  `weights_only=True`, CVE-2025-32434), `PyMuPDF` (path traversal in
  embed-extract, CVE-2026-3029), `requests` (Session cert-verification
  bypass, CVE-2024-35195), `jinja2` (sandbox breakout via the `|attr`
  filter, CVE-2024-56201/56326/CVE-2025-27516), `python-multipart` (DoS/
  ReDoS, CVE-2024-53981/24762), and an explicit `starlette` floor (DoS via
  unbounded multipart-field buffering and blocking event-loop rollover,
  CVE-2024-47874/CVE-2025-54121) rather than relying on FastAPI's own
  looser transitive floor. See `requirements.txt` / `setup.py` for the
  per-package citations.

### v3.0.0 (August 2026)
- **NEW:** Mathematical formula checking (`aegis.detectors.math_formula`).
  Equation numbering (duplicates/gaps/out-of-order), dangling in-text
  references to equations that don't exist, orphaned equations never
  referenced, and notation conventions (exponential notation, decimal
  leading zeros, percentage-range formatting) sourced from IEEE/IET style
  manuals. Extracts equations from LaTeX source, from Word's native OMML
  math XML (previously invisible to AEGIS entirely -- `python-docx`'s
  `Paragraph.text` silently skips every `.docx` equation), or via
  text-pattern heuristics for PDF/TXT. Pure Python, no ML dependency.
- **NEW:** Grammar & language convention checking
  (`aegis.detectors.grammar`). Contractions, US/UK spelling-consistency
  detection across 30+ word pairs, subject/verb agreement heuristics,
  common usage errors, and readability metrics -- fully offline via regex
  + optional spaCy, no Java runtime or external grammar service required.
- **NEW:** Per-venue publisher guideline compliance
  (`aegis.guidelines`). Runs the math/grammar findings against IEEE, ACM,
  BCS, IET, and ISACA's own sourced style guidance **separately** (not one
  merged rule set) via `aegis guidelines <file> --venues ...` or `aegis
  analyze ... --guidelines all`. Every rule cites its source; results are
  advisory (`PASS`/`NEEDS_REVIEW`/`NOT_ENOUGH_DATA`), never `FAIL` --
  these are style conventions, not misconduct findings, and are never
  factored into `overall_risk`.

### v2.5.0 (August 2026)
- **FIX (correctness, high severity):** Target-publisher keyword matching
  (`publisher_registry.classify_publisher` / `claimed_publisher`) used bare
  substring containment on short, generic venue keywords ("iet", "iete",
  "acm", "bcs"). This false-matched inside unrelated words -- a reference
  mentioning a "quiet cooling system" was classified as claiming IET, one
  mentioning noise being "quieted" was classified as claiming IETE, and a
  "pacman-style scheduling" reference was classified as claiming ACM --
  each producing a spurious `VENUE_MISMATCH` flag with no real venue claim
  present. Matching now requires the keyword not be glued to a letter/digit
  on either side (whole-word/phrase match), eliminating the collision
  while leaving genuine "IEEE Trans...", "Proc. ACM...", "IET
  Communications" matches unaffected.
- **NEW:** GPT-4/GPT-5-era lexical-tell signal in the AI content detector.
  GPT-2 perplexity/burstiness -- the detector's core signal -- was designed
  against GPT-2-era output and under-detects frontier chat models
  (GPT-4o-, GPT-5-class, and comparably RLHF-tuned models), which produce
  far more fluent, human-like perplexity and burstiness than GPT-2 ever
  did. Adds a complementary lexical signal (`GPT_TELL_PHRASES`) covering
  transition/elevation vocabulary disproportionately common in
  ChatGPT/GPT-4/GPT-5-family output ("delve into", "underscores", "pivotal
  role", "leverage", "in conclusion", ...), reported per-paragraph as
  `gpt_tell_density` and folded into the ensemble score at a modest, fixed
  weight alongside perplexity/burstiness/stylometrics -- a hit is a
  stylistic tell, not proof of AI authorship, consistent with this
  project's existing no-overclaiming stance (see watermark detector).

### v2.4.0 (August 2026)
- **NEW:** Target-Publisher Verification module (detector #11), scoping
  citation and duplicate-submission checks to IEEE, ACM, Elsevier, IET,
  IETE, and BCS. Adds `venue_verification` to every report: per-venue
  verified-citation counts, `VENUE_MISMATCH` flags when a reference claims
  one of these six venues but its DOI resolves elsewhere, and a
  duplicate/prior-publication search scoped per venue via Crossref
  (member id for IEEE/ACM/Elsevier/IET; DOI-prefix + container-title
  match for IETE/BCS, which don't hold independent Crossref membership).
  Configurable via `--target-publishers` (CLI) / `venue_target_publishers`
  (Python API); enabled by default, adds no new required dependency (reuses
  the existing `requests` + Crossref integration).

### v2.3.0 (July 2026)
Follow-up audit fixes from testing against real manuscripts, plus CI/security
hardening. Second consecutive minor bump for behavioral fixes, not a patch:
- **FIX (correctness, high severity):** DOCX paragraphs were joined with a
  single `\n`, but paragraph-level detectors (AI content, n-gram) split on
  `\n\n+` to find paragraph boundaries -- every DOCX submission silently
  collapsed into one giant "paragraph," disabling paragraph-level AI/n-gram
  detection entirely for that format. Also now extracts table cell text,
  previously dropped completely.
- **FIX (correctness, high severity):** A single low-confidence reference
  verdict (even from one detected citation) could read as "100% Citation
  Issues" and independently force `overall_risk` to CRITICAL. Citation
  findings now only influence risk once there's an adequate sample
  (>=5 references, >=80% verification coverage); below that, the report
  says `"assessment": "INCONCLUSIVE"` instead of a false-confidence verdict.
  `UNRESOLVABLE` verdicts (network/parse failures) no longer count toward
  `citation_score` either -- only confirmed `HALLUCINATED`/`MISMATCH` do.
- **FIX (correctness):** DataCite-registered DOIs (arXiv's `10.48550/*`
  prefix, etc.) previously only got a generic "not independently verified"
  pass-through after the Crossref-404/agency-check fix in v2.2.0. AEGIS now
  queries DataCite's own REST API for real title/author/year metadata and
  runs the same comparison used for Crossref results.
- **FIX (correctness):** Reference title extraction sometimes returned an
  author-list fragment (e.g. "Gentyala, F", "Mireshghallah, K") as the
  "title" when splitting on ". " hit an abbreviated author initial before
  reaching the real title -- a long-known false-positive source. Now
  prefers a quoted title (present in most citation styles) and, in the
  fallback path, explicitly skips fragments matching the surname+initial
  shape instead of returning the first sufficiently-long fragment.
- **FIX (transparency):** The report footer claimed "no data transmitted to
  third parties" unconditionally, even though citation checking contacts
  Crossref/DataCite and citation-network analysis contacts OpenAlex by
  default. Reports now include `network_activity` stating exactly which
  services (if any) were contacted for that specific run.
- **NEW:** `detector_status` in every report: each of the 9 detectors reports
  `completed` / `disabled` / `unavailable` / `failed` with a reason. A 0.0
  score used to be ambiguous between "ran and found nothing," "was disabled,"
  "had no corpus to compare against," and "raised an exception that got
  logged and silently swallowed" -- these are now distinguishable.
- **FIX (security):** Pinned the GPT-2 / GPT-2-medium model revisions used
  by the AI content detector (bandit B615: unpinned Hugging Face downloads)
  and marked the watermark heuristic's non-cryptographic MD5 bucketing hash
  as `usedforsecurity=False` (bandit B324).
- **NEW:** CI (GitHub Actions): test matrix across Python 3.10-3.12 with a
  coverage gate (60%, the current baseline -- 80% is a follow-up target,
  not enforced yet), `ruff check` (pinned to the version actually run
  against this codebase, not "latest" -- a ruff minor release changing
  default rules would otherwise break this gate with no code change),
  `bandit`, and a Docker build + healthcheck smoke test. `pip-audit` runs
  for visibility but doesn't block on transitive-dependency CVEs.
- **CHANGED:** Dropped Python 3.9 support. It reached end of life in
  October 2025, and spacy's current dependency chain (`thinc>=8.3.12`) no
  longer publishes a build for it -- the full `[ml,nlp,bib]` install is no
  longer installable on 3.9 regardless of anything in this project.
  `python_requires` is now `>=3.10`.

### v2.2.0 (July 2026)
Behavioral and security fixes from an independent audit -- not documentation-only,
so this is a minor version bump rather than a patch:
- **FIX (correctness, high severity):** ESL calibration multipliers were inverted --
  values below 1.0 *lowered* the AI-flagging threshold for non-native languages,
  making false positives against ESL writers *more* likely, the opposite of the
  documented intent. Multipliers are now >1.0, raising the threshold instead.
- **FIX (correctness):** A Crossref 404 was treated as proof a citation was
  hallucinated (confidence 0.95), but Crossref only covers Crossref-registered
  DOIs -- DataCite-registered DOIs (e.g. arXiv's `10.48550/*` prefix) always 404
  there even when valid. Now checks the DOI's registration agency first and
  returns `NOT_FOUND_IN_CROSSREF` instead of `HALLUCINATED` when appropriate.
  Timeouts/429/5xx now return `UNAVAILABLE` rather than being folded into a
  verdict about the citation.
- **FIX (correctness, data loss):** `CorpusIndexer` reloaded document metadata
  after a restart but not the actual document text, so `build_indices()` would
  silently rebuild from an empty corpus and drop every previously-indexed
  document. Document text is now persisted and reloaded correctly.
- **FIX (security):** Replaced pickle-based corpus/index serialization with
  JSON -- the REST API's `/corpus/add` + `/corpus/build` wrote to the same
  directory `/analyze` deserialized via `pickle.load`, an arbitrary-code-
  execution risk if that directory were ever writable by an untrusted party.
- **FIX (security):** The REST API had no authentication, no upload size limit,
  and no concurrency limit. Added optional `AEGIS_API_KEY` header auth (all
  routes except `/health`), `AEGIS_MAX_UPLOAD_MB` (default 50MB), and
  `AEGIS_MAX_CONCURRENT_JOBS` (default 2, returns 503 instead of queuing
  unboundedly).
  API version now reports `aegis.__version__` instead of a hardcoded `1.0.0`.
- **FIX:** Report JSON/HTML hardcoded `"aegis_version": "2.1.0"` and a stale
  footer version instead of using `aegis.__version__`. `source_breakdown` keys
  (document labels) were interpolated into HTML unescaped. `citation_network`
  and `coherence` detector results were produced by the pipeline but never
  appeared in the JSON report or HTML output -- both are now included.
- **NEW:** `aegis batch` CLI command and `POST /batch` API endpoint. Both were
  documented in the README and on the GitHub Pages site already, but neither
  existed -- `aegis batch` returned "Error: No such command 'batch'". Both now
  wire in the existing (previously untested) `BatchAnalyzer` detector.
- **FIX (Docker):** the healthcheck ran `curl`, which the image never
  installed, so it always failed. Replaced with a Python-based check. Added a
  non-root user, removed a silently-swallowed model-download failure, stopped
  installing dependencies twice (`requirements.txt` + editable install
  overlapped almost entirely), pinned the base image to a content digest, and
  added CPU/memory limits + localhost-only port binding to docker-compose.yml.
- **CHANGED:** Softened several unqualified claims on the README and GitHub
  Pages site ("Production Stable" -> "Beta -- Human Review Required", "Zero
  Blind Spots", "Closes Every Gap", "Enterprise-Ready", "Defensible in any
  hearing") given the correctness bugs found in this audit, and corrected a
  privacy claim that didn't account for Crossref/OpenAlex citation lookups.

### v2.1.1 (July 2026)
- **FIX:** Replaced unsourced comparison-table claims and stats on the README and GitHub Pages
  site with cited sources (Liang et al. 2023 for ESL false-positive bias; Walters & Wilder 2023
  for citation fabrication rates) and hedged "Not public" language for competitor capabilities
  that aren't independently verifiable
- **FIX:** Removed invented per-submission dollar figures for competitor pricing (no public
  source existed for several of them); replaced with pricing-model descriptions
- **FIX:** Corrected Liang et al. (2023) citation -- published in *Patterns* (Cell Press), not
  *Science*
- **FIX:** Stale "AEGIS v2.0" heading/table references updated to v2.1

### v2.1.0 (July 2026)
- **FIX:** Watermark heuristic could unconditionally force `overall_risk` to `CRITICAL`; it now
  never affects the risk score in experimental mode and is capped at +1 level even in a
  hypothetical validated-scheme mode
- **NEW:** `WatermarkMode` (`disabled` / `experimental` / `verified_scheme`) and `--watermark-mode` CLI flag
- **CHANGED:** Watermark verdicts renamed to `STATISTICAL_ANOMALY` / `NO_STATISTICAL_ANOMALY` / etc.;
  the old definitive `WATERMARKED` verdict is gone
- **FIX:** Removed unsupported false-positive-rate and GPT-4/Gemini-detection claims from
  the README and GitHub Pages site

### v2.0.0 (June 2026)
- **NEW:** LLM Watermark Detector (Kirchenbauer z-test + entropy + rank skew)
- **NEW:** Citation Network Analyzer (self-citation inflation, predatory journals, OpenAlex)
- **NEW:** Semantic Coherence Analyzer (discourse connectors, sentence uniformity, MTLD)
- **NEW:** Batch / Classroom Analyzer (essay mill detection, pairwise similarity matrix)
- **NEW:** `aegis batch` CLI command
- **IMPROVED:** Pipeline now runs 10 detectors in sequence with unified risk scoring
- **IMPROVED:** JSON report includes all v2.0 detector outputs
- **IMPROVED:** setup.py bumped to stable (5 - Production/Stable)

### v1.0.0 (May 2026)
- Initial release: citation integrity, ESL-calibrated AI detection, SBERT semantic similarity,
  MinHash n-gram, Burrows' Delta stylometrics, self-plagiarism detection, REST API + CLI
