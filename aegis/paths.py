"""Default locations for AEGIS user data (index, reports, .env).

Everything lives under ~/.aegis unless overridden by environment variables,
so the CLI, the web UI and the MCP server all see the same corpus and reports
regardless of the directory they were started from.
"""

from __future__ import annotations

import os
from pathlib import Path


def aegis_home() -> Path:
    return Path(os.environ.get("AEGIS_HOME", Path.home() / ".aegis")).expanduser()


def _resolve(env_var: str, legacy_name: str, home_name: str) -> Path:
    # Precedence: explicit env var > a pre-3.2 ./aegis_index or ./aegis_reports
    # in the current directory (so existing checkouts keep their corpus) >
    # the shared ~/.aegis location.
    if os.environ.get(env_var):
        return Path(os.environ[env_var]).expanduser()
    legacy = Path.cwd() / legacy_name
    if legacy.is_dir():
        return legacy
    return aegis_home() / home_name


def default_index_dir() -> Path:
    return _resolve("AEGIS_INDEX_DIR", "aegis_index", "index")


def default_report_dir() -> Path:
    return _resolve("AEGIS_REPORT_DIR", "aegis_reports", "reports")


def load_env_file(path: str | os.PathLike | None = None) -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing values.

    With no explicit path, reads AEGIS_ENV_FILE if set, otherwise ./.env
    (the file install.bat creates from .env.example) and then ~/.aegis/.env.
    """
    if path is not None:
        candidates = [Path(path)]
    elif os.environ.get("AEGIS_ENV_FILE"):
        candidates = [Path(os.environ["AEGIS_ENV_FILE"])]
    else:
        candidates = [Path.cwd() / ".env", aegis_home() / ".env"]
    for env_path in candidates:
        env_path = env_path.expanduser()
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip().strip('"').strip("'")
                if value:
                    os.environ.setdefault(key.strip(), value)
