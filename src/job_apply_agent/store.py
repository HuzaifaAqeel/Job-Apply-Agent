"""SQLite application log: every apply/dry-run is recorded."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List


class ApplicationLog:
    def __init__(self, path: str = None):
        self.path = path or os.environ.get("LOG_DB_PATH", "applications.db")
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    job_title TEXT,
                    company TEXT,
                    mode TEXT NOT NULL,          -- dry-run | submitted
                    status TEXT NOT NULL,       -- planned | submitted | blocked
                    fields_planned INTEGER DEFAULT 0,
                    fields_filled INTEGER DEFAULT 0,
                    plan_json TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL
                )"""
            )

    def record(self, url: str, mode: str, status: str,
               job_title: str = "", company: str = "",
               plan: List[Dict[str, Any]] = None,
               note: str = "") -> int:
        plan = plan or []
        filled = sum(1 for p in plan if p.get("filled") or mode == "submitted")
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO applications
                   (url, job_title, company, mode, status, fields_planned,
                    fields_filled, plan_json, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (url, job_title, company, mode, status, len(plan), filled,
                 json.dumps(plan, default=str), note,
                 datetime.now().isoformat(timespec="seconds")),
            )
            return cur.lastrowid

    def list(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT id, url, job_title, company, mode, status,
                          fields_planned, fields_filled, created_at
                   FROM applications ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, app_id: int) -> Dict[str, Any]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM applications WHERE id = ?", (app_id,)
            ).fetchone()
        return dict(row) if row else {}
