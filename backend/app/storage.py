import csv
import sqlite3
from pathlib import Path
from typing import Iterable, List

from .models import OrgRecord, ParentEntity, RecordStatus, RunResponse


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

    def create_run(self, run_name: str, notes: str = "") -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs (run_name, status, notes)
                VALUES (?, 'queued', ?)
                """,
                (run_name, notes),
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
                SELECT run_id, run_name, status, parent_entity_count, discovered_club_count, deduped_count, notes
                FROM runs
                ORDER BY run_id DESC
                """
            ).fetchall()
        return [
            RunResponse(
                run_id=r[0],
                run_name=r[1],
                status=r[2],
                parent_entity_count=r[3],
                discovered_club_count=r[4],
                deduped_count=r[5],
                notes=r[6],
            )
            for r in rows
        ]

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
