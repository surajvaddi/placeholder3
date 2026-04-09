import csv
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
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS org_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
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
                    notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
                """
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
                INSERT INTO parent_entities (run_id, name, category, notes, source_url)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (run_id, e.name, e.category, e.notes, e.source_url or "")
                    for e in entities
                ],
            )

    def replace_org_records(self, run_id: int, records: Iterable[OrgRecord]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM org_records WHERE run_id=?", (run_id,))
            conn.executemany(
                """
                INSERT INTO org_records (
                    run_id, email, name, business_name, category, location, city, state,
                    followers, website, instagram, notes, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
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
                SELECT email, name, business_name, category, location, city, state,
                       followers, website, instagram, notes, status
                FROM org_records
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchall()
        return [
            OrgRecord(
                email=r[0],
                name=r[1],
                business_name=r[2],
                category=r[3],
                location=r[4],
                city=r[5],
                state=r[6],
                followers=r[7],
                website=r[8],
                instagram=r[9],
                notes=r[10],
                status=RecordStatus(r[11]),
            )
            for r in rows
        ]
