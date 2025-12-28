import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import time


@dataclass
class ReplicaRecord:
    # Represents one deployed replica
    app: str
    replica_id: int
    slurm_job_id: str
    status: str
    created_at: float
    log_out: str
    log_err: str


def _ensure_dir(p: Path) -> None:
    # Ensure parent directory exists
    p.parent.mkdir(parents=True, exist_ok=True)


class StateDB:
    def __init__(self, db_path: Path):
        # Initialize database file
        _ensure_dir(db_path)
        self.db_path = db_path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        # Open SQLite connection
        return sqlite3.connect(str(self.db_path))

    def _init(self) -> None:
        # Create tables if not existing
        with self._conn() as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS replicas (
                app TEXT NOT NULL,
                replica_id INTEGER NOT NULL,
                slurm_job_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                log_out TEXT NOT NULL,
                log_err TEXT NOT NULL,
                PRIMARY KEY (app, replica_id)
            );
            """)
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_replicas_app ON replicas(app);"
            )

    def upsert_replica(self, r: ReplicaRecord) -> None:
        # Insert or update replica record
        with self._conn() as c:
            c.execute("""
            INSERT INTO replicas(app, replica_id, slurm_job_id, status, created_at, log_out, log_err)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app, replica_id) DO UPDATE SET
              slurm_job_id=excluded.slurm_job_id,
              status=excluded.status,
              log_out=excluded.log_out,
              log_err=excluded.log_err;
            """, (
                r.app, r.replica_id, r.slurm_job_id,
                r.status, r.created_at, r.log_out, r.log_err
            ))

    def update_status(self, app: str, replica_id: int, status: str) -> None:
        # Update job status
        with self._conn() as c:
            c.execute(
                "UPDATE replicas SET status=? WHERE app=? AND replica_id=?;",
                (status, app, replica_id)
            )

    def list_replicas(self, app: str) -> List[ReplicaRecord]:
        # List all replicas of an app
        with self._conn() as c:
            rows = c.execute("""
            SELECT app, replica_id, slurm_job_id, status, created_at, log_out, log_err
            FROM replicas WHERE app=? ORDER BY replica_id;
            """, (app,)).fetchall()
        return [ReplicaRecord(*row) for row in rows]

    def get_replica(self, app: str, replica_id: int) -> Optional[ReplicaRecord]:
        # Get one replica
        with self._conn() as c:
            row = c.execute("""
            SELECT app, replica_id, slurm_job_id, status, created_at, log_out, log_err
            FROM replicas WHERE app=? AND replica_id=?;
            """, (app, replica_id)).fetchone()
        return ReplicaRecord(*row) if row else None

    def delete_app(self, app: str) -> None:
        # Remove all replicas of an app
        with self._conn() as c:
            c.execute("DELETE FROM replicas WHERE app=?;", (app,))

