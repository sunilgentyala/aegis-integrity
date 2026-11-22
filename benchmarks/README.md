# AEGIS benchmarks

Small, reproducible checks of how AEGIS behaves on cases where the right
answer is known. They are kept separate from:

1. **Unit and integration tests** (`tests/`), which check individual functions.
2. **Synthetic demonstrations** (this folder and `docs/demo/`), which show
   specific behaviour on invented data.
3. **Held-out performance evaluation** on real documents, which **does not exist
   yet** (see [What is not evaluated](#what-is-not-evaluated)).

Everything here is in category 2. Read the numbers as "this code path does
what it should on these examples", not as accuracy on real papers.

## Citation verification (`citations/`)

| File | Purpose |
|---|---|
| `synthetic_paper.md` | Short invented paper with 12 IEEE-style references. Clearly marked as synthetic; DOIs use Crossref's `10.5555` test prefix |
| `cases.json` | For each reference: the scenario, the simulated Crossref/agency response, the human ground truth, and the verdict a correct implementation should return |
| `run_eval.py` | Runs the real AEGIS parser and citation detector with every HTTP request answered from `cases.json` |
| `results.md`, `results.json` | Output of the last `--write` run, committed for review |

### Reproduce

From the repository root, after `pip install -e .`:

```bash
python benchmarks/citations/run_eval.py                 # print results
python benchmarks/citations/run_eval.py --write         # update results.md / results.json
python benchmarks/citations/run_eval.py --html docs/demo/citation_demo_report.html
```

On Windows PowerShell the commands are the same (`python` may be `py`).

No network access, API key or ML model is needed; the run takes about a
second. `tests/test_citation_benchmark.py` re-runs it in CI and fails if any
verdict changes, or if a real network connection is attempted.

### Scenarios covered

Correct reference; real DOI belonging to a different paper; wrong year;
one-year online/print difference (acceptable); invented DOI; real DOI
registered with another agency (mEDRA); Crossref timeout; Crossref rate
limit; borrowed DOI with wrong title and year; wrong first author; no DOI
and no match; no DOI but a matching title search.

### Current results

See [`citations/results.md`](citations/results.md). As of this commit:
11 of 12 verdicts match, 4 of 5 real problems are flagged, and **no correct or
unverifiable reference is labelled fabricated**. That last property is the
most important one: a timeout, a rate limit or a DOI held by another agency
must never become "hallucinated".

### Known miss

**Wrong first author (reference 10) is not detected.** The reference parser
does not extract author names from IEEE-style strings such as
`M. Fischer, "Title," ...`, so `CitationIntegrityDetector` has no claimed
author to compare. Title and year checks still work. Fixing author extraction
is tracked as a contribution idea in
[`docs/community/good-first-issues.md`](../docs/community/good-first-issues.md).

### What the metrics mean

- **Exact verdict matches**: AEGIS returned the precise verdict in `cases.json`.
- **Truth / outcome**: `ok`, `problem` (the reference is wrong or invented), or
  `cannot_verify` (AEGIS could not check it; a human must). Verdicts map to
  outcomes as: `VALID` → ok; `MISMATCH`, `HALLUCINATED` → problem; everything
  else → cannot_verify.
- **Precision / recall**: over `problem` outcomes only.
- **False fabrication claims**: references that are fine or unverifiable but
  were labelled `HALLUCINATED`.

With 12 hand-written cases these are not statistically meaningful and must
not be quoted as accuracy figures.

### Data origin and licence

All content is invented for this repository and distributed under the
project licence. No real papers, authors or DOIs are used.

## What is not evaluated

These need real or carefully licensed data and are left as future work. No
results are claimed for them:

- **AI-text detection** and the experimental **ESL calibration**: needs
  documented human and machine-written samples, including edited and
  non-native-English writing, with per-group false-positive rates.
- **Plagiarism / similarity** on a corpus: exact copy, paraphrase, quoted text
  and unrelated text, with false-positive rates.
- **Reference parsing** across real PDF/DOCX/LaTeX layouts (multi-column,
  hanging indents, BibTeX).
- **Publisher guideline checks**: rule-level precision/recall on compliant and
  deliberately non-compliant examples.

If you can contribute redistributable data for any of these, please open an
issue first so the dataset's licence and consent can be checked.
