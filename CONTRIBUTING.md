# Contributing to AEGIS

Thanks for considering a contribution. AEGIS is a small project, so the process is lightweight.

## Setup

```bash
git clone https://github.com/sunilgentyala/aegis-integrity.git
cd aegis-integrity
pip install -e ".[ml,nlp,bib]"
pytest
```

## Before opening a PR

- Add or update a test for any behavior change. Tests live in `tests/`.
- Run `pytest` locally and keep it green.
- Keep PRs scoped to one change.
- Detectors report signals, not verdicts. Avoid wording that accuses an author of misconduct.
- Venue guideline rules should cite the official author guidelines page in a code comment.

## Reporting bugs

Open an issue with what you ran, what you expected and what you got. For false positives or negatives, include a short non-confidential text snippet that reproduces it.

## Security

Do not open a public issue for vulnerabilities. See [SECURITY.md](SECURITY.md).

## Where to start

Look for issues labeled [`good first issue`](https://github.com/sunilgentyala/aegis-integrity/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) or [`help wanted`](https://github.com/sunilgentyala/aegis-integrity/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22). Questions are welcome in Discussions.
