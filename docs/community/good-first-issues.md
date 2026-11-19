# Contribution ideas

Small, self-contained tasks for new contributors. These are **drafts**: they
are not all open issues yet. If you want to take one, open an issue (or
comment on the linked one) first so work is not duplicated.

Each idea lists where to look and how to know it is done. All of them can
be tested without network access or ML models.

## 1. Extract author names from IEEE-style references

**Why:** wrong first authors are currently missed. `benchmarks/citations/`
reference 10 cites "M. Fischer" for a paper by Garcia and AEGIS returns
`VALID`, because `ParsedReference.authors` is empty for strings like
`M. Fischer and N. Oduya, "Title," Journal, 2022.`

**Where:** `DocumentParser._extract_references_heuristic` in
`aegis/core/document.py` (around the `ParsedReference(...)` construction).

**Done when:** authors are parsed for common IEEE/ACM patterns, new unit
tests cover them, and `python benchmarks/citations/run_eval.py --write`
shows reference 10 as `MISMATCH` with no other verdict changing.

## 2. Make reference keys match the paper's numbering

**Why:** reports label `[1]` as `ref_0`, `[2]` as `ref_1`, and so on, which is
easy to misread (see `docs/demo/citation_demo_report.html`).

**Where:** `cite_key=f"ref_{i}"` in `aegis/core/document.py`.

**Done when:** keys use the number printed in the reference list when there
is one (`[12]` → `12` or `ref_12`), fall back to one-based numbering
otherwise, and existing tests are updated.

## 3. Friendly error for an invalid `AEGIS_MAX_FILE_MB`

**Why:** `aegis/mcp_server.py` runs `int(os.environ.get("AEGIS_MAX_FILE_MB", "50"))`
at import time, so a value like `50MB` stops the MCP server from starting
with a bare `ValueError`.

**Done when:** an invalid value falls back to 50 with a warning on stderr
(never stdout, which carries MCP traffic), with a test.

## 4. Avoid report filename collisions

**Why:** MCP analysis tools save `<stem>_report.html`. Two different papers
called `paper.pdf` in different folders overwrite each other's reports.

**Where:** `aegis_analyze_paper`, `aegis_check_citations` and
`aegis_check_guidelines` in `aegis/mcp_server.py`.

**Done when:** the filename includes a short hash of the resolved input path
(or a timestamp), the change is tested, and the tool docstrings mention it.

## 5. Unit tests for the grammar detector

Existing issue: [#26](https://github.com/sunilgentyala/aegis-integrity/issues/26).

## 6. Springer Nature guideline profile

Existing issue: [#24](https://github.com/sunilgentyala/aegis-integrity/issues/24).
Every rule must cite Springer Nature's official author guidelines in a code comment.

## 7. More citation benchmark cases

**Why:** the benchmark has 12 cases. Useful additions: DataCite/arXiv DOIs
(`10.48550/...`), Crossref subtitle splitting, a DOI with trailing
punctuation, a reference with a URL but no DOI, HTTP 500 from Crossref.

**Where:** `benchmarks/citations/synthetic_paper.md` and `cases.json`.

**Done when:** new cases have a ground-truth label and rationale, and
`results.md` is regenerated. Keep every name, title and DOI invented.
