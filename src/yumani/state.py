from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Profile


STATE_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def project_root(value: str | None = None) -> Path:
    root = Path(value or ".").expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Project root is not a directory: {root}")
    return root


def state_dir(root: Path, profile: Profile) -> Path:
    return root / profile.state_dir_name


@dataclass
class RunRecord:
    run_id: str
    profile: str
    mode: str
    request: str
    status: str
    created_at: str
    artifact_dir: Path


class StateStore:
    def __init__(self, root: Path, profile: Profile):
        self.root = root
        self.profile = profile
        self.dir = state_dir(root, profile)
        self.db_path = self.dir / "state.db"

    def ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "runs").mkdir(exist_ok=True)
        (self.dir / "locks").mkdir(exist_ok=True)
        with self.connect() as conn:
            self.apply_schema(conn)
        self.write_projection()

    def connect(self) -> sqlite3.Connection:
        self.dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def apply_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata(
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs(
              run_id TEXT PRIMARY KEY,
              profile TEXT NOT NULL,
              model TEXT NOT NULL,
              endpoint TEXT NOT NULL,
              mode TEXT NOT NULL,
              request_hash TEXT NOT NULL,
              request TEXT NOT NULL,
              status TEXT NOT NULL,
              failure_class TEXT NOT NULL DEFAULT 'NONE',
              context_pack_hash TEXT,
              observed_result_json TEXT,
              model_claims_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events(
              event_id TEXT PRIMARY KEY,
              run_id TEXT,
              event_type TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            ("schema_version", str(STATE_SCHEMA_VERSION)),
        )

    def create_run(self, mode: str, request: str, *, status: str = "ACTIVE") -> RunRecord:
        self.ensure()
        run_id = short_id("run")
        now = utc_now()
        artifact_dir = self.dir / "runs" / run_id
        for child in ("context", "results", "logs", "snapshots"):
            (artifact_dir / child).mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            self.apply_schema(conn)
            conn.execute(
                """
                INSERT INTO runs(
                  run_id, profile, model, endpoint, mode, request_hash, request,
                  status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    self.profile.name,
                    self.profile.model,
                    self.profile.endpoint,
                    mode,
                    sha256_text(request),
                    request,
                    status,
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO events(event_id, run_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (short_id("evt"), run_id, "run_created", json.dumps({"mode": mode}), now),
            )
            conn.commit()
        (artifact_dir / "request.md").write_text(f"# Yumani Request\n\n{request}\n", encoding="utf-8")
        self.write_projection()
        return RunRecord(run_id, self.profile.name, mode, request, status, now, artifact_dir)

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        failure_class: str = "NONE",
        context_pack_hash: str | None = None,
        observed_result: dict[str, Any] | None = None,
        model_claims: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            self.apply_schema(conn)
            conn.execute(
                """
                UPDATE runs
                SET status = ?, failure_class = ?, context_pack_hash = COALESCE(?, context_pack_hash),
                    observed_result_json = COALESCE(?, observed_result_json),
                    model_claims_json = COALESCE(?, model_claims_json),
                    updated_at = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    failure_class,
                    context_pack_hash,
                    json.dumps(observed_result, ensure_ascii=False, sort_keys=True) if observed_result else None,
                    json.dumps(model_claims, ensure_ascii=False, sort_keys=True) if model_claims else None,
                    now,
                    run_id,
                ),
            )
            conn.execute(
                "INSERT INTO events(event_id, run_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    short_id("evt"),
                    run_id,
                    "run_updated",
                    json.dumps({"status": status, "failure_class": failure_class}, sort_keys=True),
                    now,
                ),
            )
            conn.commit()
        self.write_projection()

    def latest_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.db_path.exists():
            return []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def write_projection(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        runs = self.latest_runs(8) if self.db_path.exists() else []
        state_md = [
            "# Yumani State",
            "",
            f"- profile: `{self.profile.name}`",
            f"- model: `{self.profile.model}`",
            f"- endpoint: `{self.profile.endpoint}`",
            f"- updated_at: `{utc_now()}`",
            "",
            "## Recent Runs",
        ]
        if runs:
            for run in runs:
                state_md.append(f"- `{run['run_id']}` `{run['status']}` `{run['mode']}` {run['created_at']}")
        else:
            state_md.append("- No runs recorded yet.")
        (self.dir / "state.md").write_text("\n".join(state_md) + "\n", encoding="utf-8")
        manifest = {
            "schema_version": STATE_SCHEMA_VERSION,
            "profile": self.profile.name,
            "model": self.profile.model,
            "endpoint": self.profile.endpoint,
            "state_db": str(self.db_path),
            "runs": len(runs),
            "updated_at": utc_now(),
        }
        (self.dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

