# Security Policy

## Supported versions

Security fixes go into the latest release on PyPI (`pip install -U aegis-integrity`).

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private
reporting: **Security tab > Report a vulnerability** on this repository. You
should get an acknowledgement within 5 working days.

## Threat model

AEGIS is a local-first tool. The MCP server runs over stdio on your machine and
analyses documents you point it at; paper text is never uploaded. Online checks
send reference metadata (DOIs, titles, authors) to Crossref, DataCite and OpenAlex,
and the publisher duplicate-title check sends the paper's own title to Crossref.
`aegis analyze --offline` and the MCP `skip_citations=true` option make none of
these calls. Full threat model: [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).

Built-in protections:

- MCP tools read only `.pdf`, `.docx`, `.tex`, `.txt` and `.md` files, capped at
  `AEGIS_MAX_FILE_MB` (default 50 MB).
- Set `AEGIS_ALLOWED_ROOTS` (path-separated list of folders) to confine every
  tool to specific directories. Recommended when you let an agent run AEGIS.
- Tool output is stripped of control characters and truncated before it is
  returned to the model. No tool is destructive; tools that save reports or add
  to the comparison index are annotated as writing, the rest as read-only.
- DOIs found in documents are percent-encoded, and every Crossref/DataCite/
  OpenAlex request is made without following redirects.
- The MCP server never loads `./.env`; only `~/.aegis/.env` or `AEGIS_ENV_FILE`.
- The REST API supports `AEGIS_API_KEY`. Always set it if you expose the API
  beyond localhost.

Out of scope: documents are untrusted input to third-party parsers (PyMuPDF,
python-docx). Keep dependencies updated; Dependabot, CodeQL and `pip-audit` run
in CI.
