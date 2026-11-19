# AEGIS security model

This document describes what AEGIS protects, where its trust boundaries are,
which controls are implemented, which tests cover them, and what remains the
responsibility of the user or the MCP client. It covers the local deployment
that ships today (CLI, web app on localhost, REST API, and the stdio MCP
server). It does **not** describe a hosted service; none is offered.

To report a vulnerability, see [SECURITY.md](../SECURITY.md).

## Assets

| Asset | Where it lives | Why it matters |
|---|---|---|
| Manuscripts and prior works | Anywhere the user points AEGIS | Unpublished research; often confidential |
| Comparison index | `AEGIS_INDEX_DIR` (default `~/.aegis/index`) | Derived text/embeddings of indexed papers |
| HTML/JSON reports | `AEGIS_REPORT_DIR` (default `~/.aegis/reports`) | Contain excerpts and findings |
| Other files on the machine | Everywhere else | Must not be readable through AEGIS tools |
| Secrets in `.env` | `~/.aegis/.env` or `AEGIS_ENV_FILE` | e.g. `HF_TOKEN`, `AEGIS_API_KEY` |

## Trust boundaries

```text
 MCP client / LLM agent  (untrusted arguments)
          |  stdio
          v
 aegis-mcp  --validates paths, venues, sizes-->  python -m aegis (child process)
                                                     |
             local files (untrusted content) <-------+-------> Crossref / DataCite / OpenAlex
                                                     |          (optional, metadata only)
                                                     +-------> Hugging Face (first-run model download)
```

1. **Tool arguments are untrusted.** An LLM chooses the paths and options, and
   may have been steered by a prompt injection elsewhere.
2. **Document content is untrusted.** Papers can contain hostile text, malformed
   structures aimed at parsers, or instructions addressed to the agent.
3. **Network responses are untrusted.** Metadata APIs are treated as data sources,
   not as authorities that can redirect AEGIS elsewhere.

## What is sent over the network

| Check | Destination | Data sent | How to turn it off |
|---|---|---|---|
| Citation verification | Crossref, DataCite | DOIs; reference titles/authors for title search | `--no-citations` or `--offline` |
| Citation network | OpenAlex | DOIs of up to 10 references | `--offline` |
| Publisher duplicate-title search | Crossref | **The paper's own title** (PDF/DOCX) | `--no-venue-check` or `--offline` |
| `aegis doctor` / `aegis_status` | Crossref | A connectivity `HEAD` request, no document data | `GET /status?offline=true` (API) |
| First-run model download | Hugging Face | Model requests for pinned revisions | `--no-ai --no-semantic`, or warm the cache once |

Document text is never sent. `aegis analyze --offline`, the MCP option
`skip_citations=true`, the REST API `offline=true` and the web app's
Private/offline mode make no Crossref/DataCite/OpenAlex calls.

## Threats, controls and tests

| Threat | Control | Test | Limitation |
|---|---|---|---|
| Agent reads arbitrary files (`~/.ssh/id_rsa`) | Extension allow-list (`.pdf .docx .tex .txt .md`) checked on the resolved path | `test_rejects_non_document_extension`, `test_document_named_symlink_to_non_document_is_rejected` | Any document-type file is readable when no root is set |
| Agent escapes the allowed folders | `AEGIS_ALLOWED_ROOTS`, checked after `resolve()` with `Path.is_relative_to` | `test_allowed_roots_blocks_outside`, `test_traversal_resolves_outside_root`, `test_symlink_inside_root_pointing_outside_is_rejected`, `test_sibling_prefix_is_not_inside_root`, `test_multiple_allowed_roots` | **Unrestricted by default.** Set it whenever an agent drives AEGIS. The check and the later read are separate steps, so a local attacker who can swap files in between (TOCTOU) is out of scope |
| Huge files or folders exhaust memory/time | `AEGIS_MAX_FILE_MB` (default 50), 10,000-entry cap on prior-works folders, per-tool timeouts with process-tree kill | `test_size_cap`, `test_prior_works_dir_checked` | Parser CPU use within the limit is not bounded |
| Path parsed as a CLI option (`-x.pdf`) | Paths passed as absolute resolved paths; label passed as `--label=` | `test_abs_path_never_option_like` | |
| Venue argument injection | Venue names validated against a fixed set | `test_unknown_venue_rejected` | |
| Terminal/escape-sequence injection into the model | ANSI and control characters stripped; output capped at 60,000 characters | `test_output_sanitized_and_truncated` | Plain-text instructions inside a paper are still returned as excerpts |
| Prompt injection via document text | Output is analysis text, not commands; AEGIS never executes document content | (design) | **The MCP client/LLM must treat excerpts as data.** Regex filtering cannot reliably detect injected instructions and would corrupt legitimate text, so AEGIS does not attempt it |
| SSRF/URL tricks via DOIs | DOIs percent-encoded; fixed API hosts; no redirects followed on any metadata request | `test_safe_doi_neutralises_url_metacharacters`, `test_metadata_lookups_never_follow_redirects` | |
| Unexpected network use when the user asked for offline | `--offline` sets every network-capable detector offline; MCP `skip_citations` passes it | `test_cli_offline_makes_no_network_calls`, `test_mcp_skip_citations_requests_full_offline`, control `test_cli_without_offline_sends_title_to_crossref` | Model downloads are separate (see table above) |
| Client misjudges a tool's side effects | Accurate MCP annotations: no tool destructive; report-writing and index-adding tools not read-only | `test_no_tool_is_destructive`, `test_tools_that_write_are_not_read_only`, `test_pure_read_tools_are_read_only`, `test_open_world_hint_matches_network_use` | A re-run on a same-named file replaces that file's earlier AEGIS report |
| Malicious `.env` in an untrusted working directory | MCP server never loads `./.env`; only `AEGIS_ENV_FILE` or `~/.aegis/.env` | (code: `aegis/mcp_server.py`) | |
| Script injection in HTML reports | Report values HTML-escaped; web app inserts text with `textContent` | `tests/test_detectors.py` (`ReportGenerator._esc`, `test_source_breakdown_key_is_html_escaped`) | Review the report renderer when adding sections |
| Unauthenticated REST API exposed on a network | Binds to `127.0.0.1` by default; optional `AEGIS_API_KEY`; warning logged when unset | `tests/test_api.py` | Exposing the API beyond localhost without a key and TLS is unsupported |
| Vulnerable dependencies (PyMuPDF, transformers, ...) | Version floors past known CVEs; Dependabot, CodeQL, blocking `pip-audit` in CI | CI | Parsers still process untrusted files; keep them updated |

Unless another file is named, the tests listed above are in
`tests/test_mcp_hardening.py` and `tests/test_mcp_security.py`. They run
without network access or model downloads.

## Recommended configuration when an agent drives AEGIS

```json
"env": {
  "AEGIS_ALLOWED_ROOTS": "C:\\path\\to\\papers",
  "AEGIS_MAX_FILE_MB": "50",
  "AEGIS_INDEX_DIR": "C:\\path\\to\\aegis-data\\index",
  "AEGIS_REPORT_DIR": "C:\\path\\to\\aegis-data\\reports"
}
```

On macOS/Linux use forward-slash paths; separate multiple roots with `;` on
Windows and `:` elsewhere.

## Out of scope

- A hosted/multi-user deployment. That would need authentication, per-user
  storage, upload handling and tenant isolation, none of which exist today.
- Attackers who already control the local user account.
- Correctness of detector verdicts; see the limitations section of the README.
