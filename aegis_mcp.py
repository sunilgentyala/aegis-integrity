r"""Backward-compatible launcher for the AEGIS MCP server.

Existing MCP client configs that run ``python aegis_mcp.py`` from a source
checkout keep working: this shim points the server at the checkout's own
aegis_index/, aegis_reports/ and .env (the pre-3.2 layout) and then starts
the packaged server in aegis/mcp_server.py.

New installs should use the ``aegis-mcp`` console script instead.
"""

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
os.environ.setdefault("AEGIS_INDEX_DIR", str(_HERE / "aegis_index"))
os.environ.setdefault("AEGIS_REPORT_DIR", str(_HERE / "aegis_reports"))
os.environ.setdefault("AEGIS_ENV_FILE", str(_HERE / ".env"))

from aegis.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
