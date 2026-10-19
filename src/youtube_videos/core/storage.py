"""SQLite is the source of truth. WAL and transactional event recording."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class Store:
    def __init__(self, location: Path):
        location.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(location)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, source TEXT NOT NULL, source_root TEXT NOT NULL,
              work_dir TEXT NOT NULL, config TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stages (
              run_id TEXT NOT NULL, stage_id TEXT NOT NULL, plugin TEXT NOT NULL,
              status TEXT NOT NULL, output TEXT NOT NULL, updated_at TEXT NOT NULL,
              PRIMARY KEY (run_id, stage_id), FOREIGN KEY (run_id) REFERENCES runs(id)
            );
            CREATE TABLE IF NOT EXISTS decisions (
              run_id TEXT NOT NULL, gate TEXT NOT NULL, decision TEXT NOT NULL,
              snapshot TEXT NOT NULL, decided_at TEXT NOT NULL,
              PRIMARY KEY (run_id, gate)
            );
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
              type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
            );
        """)
        self.db.commit()

    def create(self, run_id: str, source: Path, root: Path, work: Path, config: dict):
        ts = now()
        with self.db:
            self.db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (run_id, str(source), str(root), str(work), encode(config), "created", ts, ts))

    def get(self, run_id: str) -> dict:
        row = self.db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown run: {run_id}")
        result = dict(row)
        result["config"] = json.loads(result["config"])
        return result

    def set_status(self, run_id: str, status: str):
        with self.db:
            self.db.execute("UPDATE runs SET status=?, updated_at=? WHERE id=?", (status, now(), run_id))

    def stage(self, run_id: str, stage_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM stages WHERE run_id=? AND stage_id=?", (run_id, stage_id)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["output"] = json.loads(result["output"])
        return result

    def stage_outputs(self, run_id: str) -> dict[str, dict]:
        rows = self.db.execute("SELECT stage_id, output FROM stages WHERE run_id=? AND status='done'", (run_id,))
        return {r["stage_id"]: json.loads(r["output"]) for r in rows}

    def save_stage(self, run_id: str, stage_id: str, plugin: str, status: str, output: dict):
        with self.db:
            self.db.execute("INSERT INTO stages VALUES (?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(run_id,stage_id) DO UPDATE SET plugin=excluded.plugin, "
                            "status=excluded.status, output=excluded.output, updated_at=excluded.updated_at",
                            (run_id, stage_id, plugin, status, encode(output), now()))

    def decision(self, run_id: str, gate: str) -> dict | None:
        row = self.db.execute("SELECT * FROM decisions WHERE run_id=? AND gate=?", (run_id, gate)).fetchone()
        return dict(row) if row else None

    def decide(self, run_id: str, gate: str, verdict: str, snapshot: str):
        if verdict not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        with self.db:
            self.db.execute("INSERT INTO decisions VALUES (?, ?, ?, ?, ?) "
                            "ON CONFLICT(run_id,gate) DO UPDATE SET decision=excluded.decision, "
                            "snapshot=excluded.snapshot, decided_at=excluded.decided_at",
                            (run_id, gate, verdict, snapshot, now()))
            self.db.execute("INSERT INTO events(run_id,type,payload,created_at) VALUES (?,?,?,?)",
                            (run_id, "review.decided", encode({"gate": gate, "decision": verdict,
                                                                "snapshot": snapshot}), now()))

    def event(self, run_id: str, event_type: str, payload: dict, max_events: int) -> dict:
        count = self.db.execute("SELECT COUNT(*) FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
        if count >= max_events:
            raise RuntimeError(f"Event cap reached for {run_id}")
        with self.db:
            cur = self.db.execute("INSERT INTO events(run_id,type,payload,created_at) VALUES (?,?,?,?)",
                                  (run_id, event_type, encode(payload), now()))
        return {"schema": "youtube-videos.event.v1", "id": cur.lastrowid, "run_id": run_id,
                "type": event_type, "payload": payload}

    def events(self, run_id: str) -> list[dict]:
        rows = self.db.execute("SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,))
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def close(self):
        self.db.close()
