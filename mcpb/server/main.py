"""Claude Desktop extension entry point for AEGIS.

The extension does not bundle AEGIS itself (PyTorch alone is ~2 GB); it runs
the MCP server from the AEGIS package installed in the Python the user
chose in the extension settings.
"""

import os
import sys

# An empty optional setting arrives as "" -- drop it so AEGIS's own defaults apply.
for _key in ("AEGIS_INDEX_DIR", "AEGIS_CITATION_EMAIL"):
    if not os.environ.get(_key, "").strip():
        os.environ.pop(_key, None)

try:
    from aegis.mcp_server import main
except ImportError as exc:
    sys.stderr.write(
        "AEGIS is not installed in this Python (%s).\n"
        "Install it with:\n"
        '  pip install "aegis-integrity[mcp,ml] @ git+https://github.com/sunilgentyala/aegis-integrity"\n'
        "then point the extension's 'Python with AEGIS installed' setting at that python.\n"
        "Details: %s\n" % (sys.executable, exc)
    )
    sys.exit(1)

if __name__ == "__main__":
    main()
