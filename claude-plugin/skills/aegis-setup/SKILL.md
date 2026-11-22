---
name: aegis-setup
description: Install or repair AEGIS so its tools work in Claude - use when the aegis-integrity tools are missing, the MCP server fails to start ("aegis-mcp" not found), or aegis_status reports checks as missing or limited.
---

# Setting up AEGIS

The plugin starts the `aegis-mcp` command, which comes from the AEGIS Python
package. It needs Python 3.10 or newer.

## Install

Run in a terminal (offer to run it for the user):

```
pip install "aegis-integrity[mcp,ml] @ git+https://github.com/sunilgentyala/aegis-integrity"
```

- `mcp` is required for Claude. `ml` adds AI-writing and paraphrase
  detection (about 2 GB with PyTorch); leave it out for a light install that
  still verifies references and checks style.
- Prefer installing into a virtual environment. `aegis-mcp` must then be on
  the PATH that Claude uses; if it isn't, give the full path to the
  executable in the MCP settings instead.

Then restart Claude so the MCP server starts, and call `aegis_status`.

## Optional, recommended

- Download the AI models once so the first check is fast:
  `aegis doctor --warm-up`
- Give Crossref a contact email so lookups aren't throttled: add
  `AEGIS_CITATION_EMAIL=you@example.org` to `~/.aegis/.env`.
- Build a comparison library so copied-text checks have something to
  compare against: `aegis index build <folder of papers>`, or use the
  "My comparison library" tab in `aegis ui`.

## Troubleshooting

- Run `aegis doctor` in a terminal: it lists every capability, whether it is
  ready, and the exact command that fixes it.
- A timeout on the first full analysis is almost always the one-time model
  download; `aegis doctor --warm-up` avoids it.
