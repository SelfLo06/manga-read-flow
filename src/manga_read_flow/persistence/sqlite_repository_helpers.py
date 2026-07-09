from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from urllib.parse import quote


def connect_existing(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(sqlite_readwrite_uri(path), uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def sqlite_readwrite_uri(path: Path) -> str:
    return f"file:{quote(str(path), safe='/')}?mode=rw"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
