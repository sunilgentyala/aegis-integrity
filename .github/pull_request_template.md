## What and why

<!-- One change per PR. Link the issue it addresses, e.g. "Closes #25". -->

## Checklist

- [ ] Tests added or updated for any behaviour change (`tests/`)
- [ ] `pytest tests` passes locally
- [ ] `ruff check aegis/` passes
- [ ] No new network calls, or they are documented in `docs/SECURITY_MODEL.md` and respect `--offline`
- [ ] MCP tool annotations still match what each tool does (read-only, writes, network)
- [ ] User-facing wording describes signals for human review, not misconduct verdicts
- [ ] Publisher rules cite the official guideline page in a code comment
- [ ] No confidential manuscripts, personal data, secrets or local paths in fixtures or logs
- [ ] If `python benchmarks/citations/run_eval.py` results changed, `--write` was re-run and the change is explained below

## Notes for the reviewer
