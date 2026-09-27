"""Durable single-submit journal with cross-process SQLite locking."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .private_storage import private_file


class SubmissionUncertain(RuntimeError):
    """A billable submit may have reached the provider; never POST this intent again."""


@dataclass(frozen=True)
class Intent:
    identity: str
    status: str
    prediction_id: str | None
    result_path: str | None
    detail: str | None
    intent_guard: str | None
    request_json: str | None
    payload_json: str | None
    submission_hash: str | None
    media_json: str | None
    nonce: str | None
    result_sha256: str | None


class TaskJournal:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        private_file(self.path)
        con = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        # Two first-time workers can race while SQLite switches the fresh file
        # into WAL mode. That PRAGMA may report locked before busy_timeout helps.
        try:
            for attempt in range(40):
                try:
                    con.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or attempt == 39:
                        raise
                    time.sleep(0.05)
        except Exception:
            con.close()
            raise
        con.execute("PRAGMA synchronous=FULL")
        con.execute("""CREATE TABLE IF NOT EXISTS tasks (
            identity TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            prediction_id TEXT,
            result_path TEXT,
            detail TEXT,
            intent_guard TEXT UNIQUE,
            request_json TEXT,
            payload_json TEXT,
            submission_hash TEXT,
            media_json TEXT,
            nonce TEXT,
            result_sha256 TEXT,
            updated_at REAL NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS queue_intents (
            node_key TEXT NOT NULL,
            queue_id TEXT NOT NULL,
            nonce TEXT NOT NULL,
            PRIMARY KEY(node_key,queue_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS active_intents (
            node_key TEXT PRIMARY KEY,
            nonce TEXT NOT NULL
        )""")
        columns = {row[1] for row in con.execute("PRAGMA table_info(tasks)")}
        for name, sql_type in (("request_json", "TEXT"), ("payload_json", "TEXT"), ("submission_hash", "TEXT"), ("media_json", "TEXT"), ("nonce", "TEXT"), ("intent_guard", "TEXT"), ("result_sha256", "TEXT")):
            if name not in columns:
                con.execute(f"ALTER TABLE tasks ADD COLUMN {name} {sql_type}")
        return con

    def bind_queue(self, *, node_key: str, queue_id: str, proposed_nonce: str, legacy_nonce: str | None = None) -> str:
        """Bind one queued invocation to a durable intent before any billable submit.

        New queues resume an intent once its sole POST may have happened. A
        prepared, unclaimed request can be superseded atomically. Once an
        intent finishes, the next queue starts fresh; old queue IDs keep their alias.
        """
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            prior = con.execute(
                "SELECT nonce FROM queue_intents WHERE node_key=? AND queue_id=?",
                (node_key, queue_id),
            ).fetchone()
            if prior:
                con.commit()
                return prior[0]
            active = con.execute("SELECT nonce FROM active_intents WHERE node_key=?", (node_key,)).fetchone()
            nonce = proposed_nonce
            if active:
                current = con.execute(
                    "SELECT status FROM tasks WHERE nonce=? ORDER BY updated_at DESC LIMIT 1",
                    (active[0],),
                ).fetchone()
                if current and current[0] == "prepared":
                    # A newer queue may replace a request before its sole POST claim.
                    # claim_submit uses the same write lock, so the old worker loses
                    # the claim if this update wins and cannot bill in parallel.
                    con.execute(
                        "UPDATE tasks SET status='failed',detail='Superseded before submit',updated_at=? "
                        "WHERE nonce=? AND status='prepared' AND prediction_id IS NULL",
                        (time.time(), active[0]),
                    )
                elif current is None or current[0] not in ("complete", "failed"):
                    nonce = active[0]
            elif legacy_nonce and legacy_nonce != "initial":
                legacy = con.execute(
                    "SELECT status FROM tasks WHERE nonce=? ORDER BY updated_at DESC LIMIT 1",
                    (legacy_nonce,),
                ).fetchone()
                if legacy and legacy[0] == "prepared":
                    con.execute(
                        "UPDATE tasks SET status='failed',detail='Superseded before submit',updated_at=? "
                        "WHERE nonce=? AND status='prepared' AND prediction_id IS NULL",
                        (time.time(), legacy_nonce),
                    )
                elif legacy and legacy[0] not in ("complete", "failed"):
                    nonce = legacy_nonce
            con.execute("INSERT INTO queue_intents(node_key,queue_id,nonce) VALUES(?,?,?)", (node_key, queue_id, nonce))
            con.execute(
                "INSERT INTO active_intents(node_key,nonce) VALUES(?,?) "
                "ON CONFLICT(node_key) DO UPDATE SET nonce=excluded.nonce",
                (node_key, nonce),
            )
            con.commit()
            return nonce

    def get_or_create(self, identity: str, intent_guard: str, *, request: dict | None = None, media: dict | None = None, nonce: str | None = None) -> Intent:
        request_json = compact_payload(request) if request is not None else None
        media_json = compact_payload(media) if media is not None else None
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT identity,status,prediction_id,result_path,detail,intent_guard,request_json,payload_json,submission_hash,media_json,nonce,result_sha256 FROM tasks WHERE intent_guard=?", (intent_guard,)).fetchone()
            if row is None:
                con.execute("INSERT OR IGNORE INTO tasks(identity,status,updated_at,intent_guard,request_json,media_json,nonce) VALUES(?,?,?,?,?,?,?)",
                            (identity, "prepared", time.time(), intent_guard, request_json, media_json, nonce))
                row = con.execute("SELECT identity,status,prediction_id,result_path,detail,intent_guard,request_json,payload_json,submission_hash,media_json,nonce,result_sha256 FROM tasks WHERE intent_guard=?", (intent_guard,)).fetchone()
            con.commit()
        return Intent(*row)

    def claim_submit(self, identity: str, payload: dict | None = None) -> bool:
        """Atomically grant the sole POST. A crash after this point is indeterminate."""
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            digest = hashlib.sha256(compact_payload(payload).encode("utf-8")).hexdigest() if payload is not None else None
            row = con.execute("SELECT submission_hash FROM tasks WHERE identity=?", (identity,)).fetchone()
            if row is None or (row[0] is None and digest is None):
                con.rollback()
                raise SubmissionUncertain("No frozen provider payload exists; the billable POST is blocked.")
            changed = con.execute(
                "UPDATE tasks SET status='submitting',submission_hash=COALESCE(?,submission_hash),updated_at=? WHERE identity=? AND status='prepared' AND prediction_id IS NULL",
                (digest, time.time(), identity),
            ).rowcount
            con.commit()
            return changed == 1

    def freeze_payload(self, identity: str, payload: dict) -> dict:
        encoded = compact_payload(payload)
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT payload_json FROM tasks WHERE identity=?", (identity,)).fetchone()
            if row is None:
                con.rollback()
                raise KeyError(identity)
            if row[0] is not None:
                con.commit()
                return json.loads(row[0])
            con.execute("UPDATE tasks SET payload_json=?,updated_at=? WHERE identity=? AND status='prepared'", (encoded, time.time(), identity))
            con.commit()
        return json.loads(encoded)

    def freeze_submission(self, identity: str, payload: dict) -> dict:
        encoded = compact_payload(payload)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status FROM tasks WHERE identity=?", (identity,)).fetchone()
            if row is None:
                con.rollback()
                raise KeyError(identity)
            if row[0] != "prepared":
                con.rollback()
                raise SubmissionUncertain("A frozen submission cannot change after the sole POST claim.")
            # Persist only a hash: upload URLs can be transient and must never be replayed after restart.
            con.execute("UPDATE tasks SET submission_hash=COALESCE(submission_hash,?),updated_at=? WHERE identity=? AND status='prepared'", (digest, time.time(), identity))
            con.commit()
        return json.loads(encoded)

    def record_prediction(self, identity: str, prediction_id: str) -> None:
        if not prediction_id or not isinstance(prediction_id, str):
            raise ValueError("Provider prediction ID is empty.")
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT prediction_id,status FROM tasks WHERE identity=?", (identity,)).fetchone()
            if row is None:
                con.rollback()
                raise SubmissionUncertain("The accepted prediction does not have a journaled intent; do not submit again.")
            old_id, status = row
            if old_id is not None and old_id != prediction_id:
                con.rollback()
                raise SubmissionUncertain("The intent already has a different prediction ID; its identity is immutable.")
            if status not in ("submitting", "accepted", "polling", "downloading"):
                con.rollback()
                raise SubmissionUncertain("The journal state cannot accept a prediction ID; do not submit again.")
            if status == "submitting":
                con.execute("UPDATE tasks SET status='accepted',prediction_id=?,updated_at=? WHERE identity=?", (prediction_id, time.time(), identity))
            con.commit()

    def mark(self, identity: str, status: str, *, detail: str | None = None, result_path: str | None = None, result_sha256: str | None = None) -> None:
        allowed = {"accepted", "polling", "downloading", "complete", "failed", "indeterminate"}
        if status not in allowed:
            raise ValueError("Unsupported task state.")
        safe_detail = detail[:500] if detail else None
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status FROM tasks WHERE identity=?", (identity,)).fetchone()
            if row is None:
                raise KeyError(identity)
            current = row[0]
            if current in ("complete", "failed", "indeterminate") and status != current:
                con.commit()
                return
            con.execute(
                "UPDATE tasks SET status=?,detail=?,result_path=COALESCE(?,result_path),result_sha256=COALESCE(?,result_sha256),updated_at=? WHERE identity=?",
                (status, safe_detail, result_path, result_sha256, time.time(), identity),
            )
            con.commit()

    def recover_result(self, identity: str) -> None:
        """Reopen only a completed artifact whose local file failed verification."""
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("UPDATE tasks SET status='accepted',detail=?,updated_at=? WHERE identity=? AND status='complete' AND prediction_id IS NOT NULL",
                        ("local result missing/corrupt; recover existing prediction", time.time(), identity))
            con.commit()

    def intent(self, identity: str) -> Intent:
        with closing(self._connect()) as con:
            row = con.execute("SELECT identity,status,prediction_id,result_path,detail,intent_guard,request_json,payload_json,submission_hash,media_json,nonce,result_sha256 FROM tasks WHERE identity=?", (identity,)).fetchone()
        if row is None:
            raise KeyError(identity)
        return Intent(*row)


def compact_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
