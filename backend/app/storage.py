from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Iterable, List

from .models import OrgRecord, ParentEntity, RecordStatus, RunMode, RunResponse
from .models_seeds import SeedFamily, SeedRegistryEntry, SeedRegistryStatus


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parent_entity_count INTEGER NOT NULL DEFAULT 0,
                    discovered_club_count INTEGER NOT NULL DEFAULT 0,
                    deduped_count INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT ''
                )
                """
            )
            self._ensure_column(conn, "runs", "run_mode", "TEXT NOT NULL DEFAULT 'incremental'")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS parent_entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    parent_key TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    seed_type TEXT NOT NULL DEFAULT '',
                    source_seed_id TEXT NOT NULL DEFAULT '',
                    confidence_score REAL NOT NULL DEFAULT 0,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
                """
            )
            self._ensure_column(conn, "parent_entities", "parent_key", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "parent_entities", "seed_type", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(
                conn, "parent_entities", "source_seed_id", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column(
                conn, "parent_entities", "confidence_score", "REAL NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                conn, "parent_entities", "evidence_json", "TEXT NOT NULL DEFAULT '[]'"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS org_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    parent_key TEXT NOT NULL DEFAULT '',
                    expansion_seed_id TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    business_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    city TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT '',
                    followers TEXT NOT NULL DEFAULT '',
                    website TEXT NOT NULL DEFAULT '',
                    instagram TEXT NOT NULL DEFAULT '',
                    confidence_score REAL NOT NULL DEFAULT 0,
                    review_flags_json TEXT NOT NULL DEFAULT '[]',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    source_count INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
                """
            )
            self._ensure_column(conn, "org_records", "parent_key", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(
                conn, "org_records", "expansion_seed_id", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column(
                conn, "org_records", "confidence_score", "REAL NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                conn, "org_records", "review_flags_json", "TEXT NOT NULL DEFAULT '[]'"
            )
            self._ensure_column(
                conn, "org_records", "evidence_json", "TEXT NOT NULL DEFAULT '[]'"
            )
            self._ensure_column(
                conn, "org_records", "source_count", "INTEGER NOT NULL DEFAULT 0"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seed_registry (
                    seed_id TEXT NOT NULL,
                    seed_family TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_processed_run_id INTEGER,
                    last_processed_fingerprint TEXT,
                    last_success_at TEXT,
                    status TEXT NOT NULL,
                    PRIMARY KEY (seed_id, seed_family)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processing_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    shot TEXT NOT NULL,
                    unit_key TEXT NOT NULL,
                    seed_id TEXT NOT NULL DEFAULT '',
                    expansion_seed_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_message TEXT NOT NULL DEFAULT '',
                    context_json TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_processing_history_lookup
                ON processing_history (shot, unit_key, status)
                """
            )

    def _ensure_column(
        self, conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing_columns = {row[1] for row in rows}
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    def create_run(
        self, run_name: str, notes: str = "", run_mode: RunMode = RunMode.incremental
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs (run_name, status, notes, run_mode)
                VALUES (?, 'queued', ?, ?)
                """,
                (run_name, notes, run_mode.value),
            )
            return int(cursor.lastrowid)

    def update_run_status(
        self,
        run_id: int,
        status: str,
        parent_entity_count: int | None = None,
        discovered_club_count: int | None = None,
        deduped_count: int | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))
            if parent_entity_count is not None:
                conn.execute(
                    "UPDATE runs SET parent_entity_count=? WHERE run_id=?",
                    (parent_entity_count, run_id),
                )
            if discovered_club_count is not None:
                conn.execute(
                    "UPDATE runs SET discovered_club_count=? WHERE run_id=?",
                    (discovered_club_count, run_id),
                )
            if deduped_count is not None:
                conn.execute(
                    "UPDATE runs SET deduped_count=? WHERE run_id=?",
                    (deduped_count, run_id),
                )

    def list_runs(self) -> List[RunResponse]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, run_name, status, run_mode, parent_entity_count, discovered_club_count, deduped_count, notes
                FROM runs
                ORDER BY run_id DESC
                """
            ).fetchall()
        return [
            RunResponse(
                run_id=r[0],
                run_name=r[1],
                status=r[2],
                run_mode=RunMode(r[3] or RunMode.incremental.value),
                parent_entity_count=r[4],
                discovered_club_count=r[5],
                deduped_count=r[6],
                notes=r[7],
            )
            for r in rows
        ]

    def get_seed_registry_entries(self) -> List[SeedRegistryEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT seed_id, seed_family, fingerprint, enabled, payload_json, last_seen_at,
                       last_processed_run_id, last_processed_fingerprint, last_success_at, status
                FROM seed_registry
                """
            ).fetchall()
        return [
            SeedRegistryEntry(
                seed_id=row[0],
                seed_family=SeedFamily(row[1]),
                fingerprint=row[2],
                enabled=bool(row[3]),
                payload_json=row[4],
                last_seen_at=row[5],
                last_processed_run_id=row[6],
                last_processed_fingerprint=row[7],
                last_success_at=row[8],
                status=SeedRegistryStatus(row[9]),
            )
            for row in rows
        ]

    def upsert_seed_registry_entries(self, entries: Iterable[SeedRegistryEntry]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO seed_registry (
                    seed_id, seed_family, fingerprint, enabled, payload_json, last_seen_at,
                    last_processed_run_id, last_processed_fingerprint, last_success_at, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(seed_id, seed_family) DO UPDATE SET
                    fingerprint=excluded.fingerprint,
                    enabled=excluded.enabled,
                    payload_json=excluded.payload_json,
                    last_seen_at=excluded.last_seen_at,
                    status=excluded.status
                """,
                [
                    (
                        entry.seed_id,
                        entry.seed_family.value,
                        entry.fingerprint,
                        int(entry.enabled),
                        entry.payload_json,
                        entry.last_seen_at,
                        entry.last_processed_run_id,
                        entry.last_processed_fingerprint,
                        entry.last_success_at,
                        entry.status.value,
                    )
                    for entry in entries
                ],
            )

    def mark_seed_processed(
        self,
        run_id: int,
        seed_id: str,
        seed_family: SeedFamily,
        fingerprint: str,
        processed_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE seed_registry
                SET last_processed_run_id=?,
                    last_processed_fingerprint=?,
                    last_success_at=?,
                    status=?
                WHERE seed_id=? AND seed_family=?
                """,
                (
                    run_id,
                    fingerprint,
                    processed_at,
                    SeedRegistryStatus.active.value,
                    seed_id,
                    seed_family.value,
                ),
            )

    def save_parent_entities(self, run_id: int, entities: Iterable[ParentEntity]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO parent_entities (
                    run_id, parent_key, name, category, seed_type, source_seed_id,
                    confidence_score, evidence_json, notes, source_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        e.parent_key,
                        e.name,
                        e.category,
                        e.seed_type,
                        e.source_seed_id,
                        e.confidence_score,
                        e.evidence_json,
                        e.notes,
                        e.source_url or "",
                    )
                    for e in entities
                ],
            )

    def replace_org_records(self, run_id: int, records: Iterable[OrgRecord]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM org_records WHERE run_id=?", (run_id,))
            conn.executemany(
                """
                INSERT INTO org_records (
                    run_id, parent_key, expansion_seed_id, email, name, business_name, category, location, city, state,
                    followers, website, instagram, confidence_score, review_flags_json, evidence_json,
                    source_count, notes, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        r.parent_key,
                        r.expansion_seed_id,
                        r.email,
                        r.name,
                        r.business_name,
                        r.category,
                        r.location,
                        r.city,
                        r.state,
                        r.followers,
                        r.website,
                        r.instagram,
                        r.confidence_score,
                        r.review_flags_json,
                        r.evidence_json,
                        r.source_count,
                        r.notes,
                        r.status.value,
                    )
                    for r in records
                ],
            )

    def export_csv(self, run_id: int, target_path: Path) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT email, name, business_name, category, location, city, state,
                       followers, website, instagram, notes, status
                FROM org_records
                WHERE run_id = ?
                ORDER BY business_name, state, city
                """,
                (run_id,),
            ).fetchall()

        with target_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "email",
                    "name",
                    "business_name",
                    "category",
                    "location",
                    "city",
                    "state",
                    "followers",
                    "website",
                    "instagram",
                    "notes",
                    "status",
                ]
            )
            writer.writerows(rows)
        return target_path

    def list_records(self, run_id: int) -> List[OrgRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT parent_key, expansion_seed_id, email, name, business_name, category, location, city, state,
                       followers, website, instagram, confidence_score, review_flags_json, evidence_json,
                       source_count, notes, status
                FROM org_records
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchall()
        return [
            OrgRecord(
                parent_key=r[0],
                expansion_seed_id=r[1],
                email=r[2],
                name=r[3],
                business_name=r[4],
                category=r[5],
                location=r[6],
                city=r[7],
                state=r[8],
                followers=r[9],
                website=r[10],
                instagram=r[11],
                confidence_score=r[12],
                review_flags_json=r[13],
                evidence_json=r[14],
                source_count=r[15],
                notes=r[16],
                status=RecordStatus(r[17]),
            )
            for r in rows
        ]

    def list_record_details(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT parent_key, expansion_seed_id, email, name, business_name, category, location, city, state,
                       followers, website, instagram, confidence_score, review_flags_json, evidence_json,
                       source_count, notes, status
                FROM org_records
                WHERE run_id = ?
                ORDER BY confidence_score DESC, business_name
                """,
                (run_id,),
            ).fetchall()
        details: list[dict] = []
        for row in rows:
            review_flags = json.loads(row[13] or "[]")
            evidence = json.loads(row[14] or "[]")
            details.append(
                {
                    "parent_key": row[0],
                    "expansion_seed_id": row[1],
                    "email": row[2],
                    "name": row[3],
                    "business_name": row[4],
                    "category": row[5],
                    "location": row[6],
                    "city": row[7],
                    "state": row[8],
                    "followers": row[9],
                    "website": row[10],
                    "instagram": row[11],
                    "confidence_score": row[12],
                    "review_flags": review_flags,
                    "evidence_count": len(evidence),
                    "source_count": row[15],
                    "notes": row[16],
                    "status": row[17],
                }
            )
        return details

    def list_run_logs(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT shot, unit_key, seed_id, expansion_seed_id, status, input_fingerprint,
                       started_at, completed_at, error_message, context_json
                FROM processing_history
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
        logs: list[dict] = []
        for row in rows:
            logs.append(
                {
                    "shot": row[0],
                    "unit_key": row[1],
                    "seed_id": row[2],
                    "expansion_seed_id": row[3],
                    "status": row[4],
                    "input_fingerprint": row[5],
                    "started_at": row[6],
                    "completed_at": row[7],
                    "error_message": row[8],
                    "context": json.loads(row[9] or "{}"),
                }
            )
        return logs

    def get_run_diagnostics(self, run_id: int) -> dict:
        records = self.list_record_details(run_id)
        logs = self.list_run_logs(run_id)
        review_count = sum(1 for record in records if record["review_flags"])
        average_confidence = (
            round(sum(record["confidence_score"] for record in records) / len(records), 2)
            if records
            else 0.0
        )
        rejected_count = sum(
            int(log["context"].get("rejected_count", 0)) for log in logs if log["shot"] == "shot2"
        )
        return {
            "summary": {
                "record_count": len(records),
                "review_count": review_count,
                "average_confidence": average_confidence,
                "rejected_count": rejected_count,
                "log_count": len(logs),
            },
            "logs": logs,
            "records": records[:100],
        }

    def record_processing_history(
        self,
        run_id: int,
        shot: str,
        unit_key: str,
        seed_id: str,
        expansion_seed_id: str,
        status: str,
        input_fingerprint: str,
        started_at: str,
        completed_at: str | None,
        error_message: str = "",
        context: dict | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO processing_history (
                    run_id, shot, unit_key, seed_id, expansion_seed_id, status,
                    input_fingerprint, started_at, completed_at, error_message, context_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    shot,
                    unit_key,
                    seed_id,
                    expansion_seed_id,
                    status,
                    input_fingerprint,
                    started_at,
                    completed_at,
                    error_message,
                    json.dumps(context or {}, sort_keys=True),
                ),
            )

    def get_successful_processing_fingerprints(self, shot: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ph.unit_key, ph.input_fingerprint
                FROM processing_history ph
                INNER JOIN (
                    SELECT unit_key, MAX(id) AS max_id
                    FROM processing_history
                    WHERE shot = ? AND status = 'completed'
                    GROUP BY unit_key
                ) latest
                ON ph.id = latest.max_id
                """,
                (shot,),
            ).fetchall()
        return {row[0]: row[1] for row in rows}
