# Contributing to AEGIS

Thanks for considering a contribution. AEGIS is a small project, so the process is lightweight.

## Setup

Use a virtual environment. The fast setup is enough for most changes; the
test suite runs without network access or model downloads.

```bash
git clone https://github.com/sunilgentyala/aegis-integrity.git
cd aegis-integrity
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[mcp]" pytest httpx2 ruff==0.15.12
pytest tests
ruff check aegis/
```

For changes to AI-text, semantic or stylometric detectors, install the full
set that CI uses: `pip install -e ".[ml,nlp,bib,mcp]"`.

To check citation behaviour end to end without the network, run
`python benchmarks/citations/run_eval.py` (see [benchmarks/](benchmarks/README.md)).

## Before opening a PR

- Add or update a test for any behavior change. Tests live in `tests/`.
- Run `pytest` locally and keep it green.
- Keep PRs scoped to one change.
- Detectors report signals, not verdicts. Avoid wording that accuses an author of misconduct.
- Venue guideline rules should cite the official author guidelines page in a code comment.

- Read [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) before touching file handling, MCP tools or network code. New network calls must respect `--offline`.

## Test data and manuscripts

- Never commit or attach confidential, unpublished or copyrighted manuscripts, or text you do not have the right to share.
- Prefer synthetic fixtures. Mark them as synthetic and use invented DOIs (Crossref's `10.5555` test prefix).
- Mock network calls in tests; CI must not depend on Crossref, OpenAlex or Hugging Face being reachable.

## Reporting bugs

Use the issue templates: **Bug report** for crashes and install problems, **Wrong or confusing result** for false positives and negatives. Include the AEGIS version and `aegis doctor --plain` output, and a short non-confidential snippet that reproduces the problem.

## Security

Do not open a public issue for vulnerabilities. See [SECURITY.md](SECURITY.md).

## Where to start

[docs/community/good-first-issues.md](docs/community/good-first-issues.md) lists small, well-scoped ideas with pointers into the code. The [roadmap](docs/community/roadmap.md) explains current priorities. You can also look for issues labeled [`good first issue`](https://github.com/sunilgentyala/aegis-integrity/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) or [`help wanted`](https://github.com/sunilgentyala/aegis-integrity/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22). Questions are welcome in Discussions.
