"""Local-dev hosted control plane for CodeAtlas.

This module intentionally keeps the first hosted MVP dependency-light: SQLite
for metadata, per-repo graph DB paths for isolation, and hashed bearer tokens
for demo-ready auth without external OAuth credentials.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer

TokenSubject = Literal["team", "repo"]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _commit_sha(repo_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


class HostedUser(BaseModel):
    id: str
    email: str
    name: str
    created_at: int


class HostedTeam(BaseModel):
    id: str
    slug: str
    name: str
    created_at: int


class HostedRepo(BaseModel):
    id: str
    team_id: str
    name: str
    local_path: str
    graph_db_path: str
    provider: str = "local"
    provider_repo: str | None = None
    default_branch: str | None = None
    last_commit_sha: str | None = None
    last_indexed_at: int | None = None
    last_sync_status: str = "never"
    last_error: str | None = None
    created_at: int
    updated_at: int


class HostedToken(BaseModel):
    id: str
    subject_type: TokenSubject
    subject_id: str
    name: str
    prefix: str
    scopes: list[str]
    created_at: int
    last_used_at: int | None = None
    revoked_at: int | None = None


class HostedSyncEvent(BaseModel):
    id: str
    repo_id: str
    status: str
    message: str
    parsed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: int = 0
    commit_sha: str | None = None
    created_at: int


class HostedPrincipal(BaseModel):
    token: HostedToken
    team_id: str | None = None
    repo_id: str | None = None


class IssuedToken(BaseModel):
    token: str
    token_record: HostedToken


class BootstrapResult(BaseModel):
    user: HostedUser
    team: HostedTeam
    token: str
    token_record: HostedToken


class SyncResult(BaseModel):
    repo: HostedRepo
    event: HostedSyncEvent


@dataclass(frozen=True)
class RepoRegistration:
    team_slug: str
    name: str
    local_path: Path
    provider: str = "local"
    provider_repo: str | None = None
    default_branch: str | None = None


class HostedStore:
    """SQLite metadata store for local hosted-MVP demos."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        self._conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS teams (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memberships (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, team_id)
            );
            CREATE TABLE IF NOT EXISTS repos (
                id TEXT PRIMARY KEY,
                team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                local_path TEXT NOT NULL,
                graph_db_path TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'local',
                provider_repo TEXT,
                default_branch TEXT,
                last_commit_sha TEXT,
                last_indexed_at INTEGER,
                last_sync_status TEXT NOT NULL DEFAULT 'never',
                last_error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(team_id, name)
            );
            CREATE TABLE IF NOT EXISTS tokens (
                id TEXT PRIMARY KEY,
                subject_type TEXT NOT NULL CHECK(subject_type IN ('team', 'repo')),
                subject_id TEXT NOT NULL,
                name TEXT NOT NULL,
                prefix TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                scopes TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_used_at INTEGER,
                revoked_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS sync_events (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                parsed INTEGER NOT NULL DEFAULT 0,
                skipped INTEGER NOT NULL DEFAULT 0,
                errors INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                commit_sha TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_repos_team ON repos(team_id);
            CREATE INDEX IF NOT EXISTS idx_tokens_hash ON tokens(token_hash);
            CREATE INDEX IF NOT EXISTS idx_sync_events_repo_created
                ON sync_events(repo_id, created_at DESC);
            """
        )
        self._conn.commit()

    def bootstrap_dev(
        self,
        *,
        email: str = "dev@codeatlas.local",
        name: str = "CodeAtlas Dev",
        team_slug: str = "default",
        team_name: str = "Default Team",
    ) -> BootstrapResult:
        now = _now_ms()
        user_id = self._upsert_user(email=email, name=name, created_at=now)
        team_id = self._upsert_team(slug=team_slug, name=team_name, created_at=now)
        self._conn.execute(
            """
            INSERT OR IGNORE INTO memberships (user_id, team_id, role, created_at)
            VALUES (?, ?, 'owner', ?)
            """,
            (user_id, team_id, now),
        )
        self._conn.commit()
        issued = self.create_token(
            subject_type="team",
            subject_id=team_id,
            name="dev team token",
            scopes=["hosted:read", "hosted:write", "repo:sync", "context:read"],
        )
        return BootstrapResult(
            user=self.get_user(user_id),
            team=self.get_team(team_id),
            token=issued.token,
            token_record=issued.token_record,
        )

    def _upsert_user(self, *, email: str, name: str, created_at: int) -> str:
        existing = self._conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return str(existing["id"])
        user_id = f"user_{uuid.uuid4().hex}"
        self._conn.execute(
            "INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
            (user_id, email, name, created_at),
        )
        return user_id

    def _upsert_team(self, *, slug: str, name: str, created_at: int) -> str:
        existing = self._conn.execute("SELECT id FROM teams WHERE slug = ?", (slug,)).fetchone()
        if existing:
            return str(existing["id"])
        team_id = f"team_{uuid.uuid4().hex}"
        self._conn.execute(
            "INSERT INTO teams (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
            (team_id, slug, name, created_at),
        )
        return team_id

    def create_team(self, *, slug: str, name: str) -> HostedTeam:
        now = _now_ms()
        team_id = self._upsert_team(slug=slug, name=name, created_at=now)
        self._conn.commit()
        return self.get_team(team_id)

    def get_user(self, user_id: str) -> HostedUser:
        row = self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise KeyError(f"user not found: {user_id}")
        return HostedUser.model_validate(_row_to_dict(row))

    def get_team(self, team_id_or_slug: str) -> HostedTeam:
        row = self._conn.execute(
            "SELECT * FROM teams WHERE id = ? OR slug = ?",
            (team_id_or_slug, team_id_or_slug),
        ).fetchone()
        if row is None:
            raise KeyError(f"team not found: {team_id_or_slug}")
        return HostedTeam.model_validate(_row_to_dict(row))

    def list_teams(self) -> list[HostedTeam]:
        rows = self._conn.execute("SELECT * FROM teams ORDER BY created_at ASC").fetchall()
        return [HostedTeam.model_validate(_row_to_dict(row)) for row in rows]

    def create_token(
        self,
        *,
        subject_type: TokenSubject,
        subject_id: str,
        name: str,
        scopes: list[str],
    ) -> IssuedToken:
        raw = "cat_" + secrets.token_urlsafe(32)
        prefix = raw[:12]
        token_id = f"tok_{uuid.uuid4().hex}"
        now = _now_ms()
        self._conn.execute(
            """
            INSERT INTO tokens
                (id, subject_type, subject_id, name, prefix, token_hash, scopes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token_id,
                subject_type,
                subject_id,
                name,
                prefix,
                _hash_token(raw),
                json.dumps(scopes),
                now,
            ),
        )
        self._conn.commit()
        return IssuedToken(token=raw, token_record=self.get_token(token_id))

    def get_token(self, token_id: str) -> HostedToken:
        row = self._conn.execute("SELECT * FROM tokens WHERE id = ?", (token_id,)).fetchone()
        if row is None:
            raise KeyError(f"token not found: {token_id}")
        data = _row_to_dict(row)
        data["scopes"] = json.loads(str(data["scopes"]))
        return HostedToken.model_validate(data)

    def verify_token(self, token: str) -> HostedPrincipal | None:
        row = self._conn.execute(
            "SELECT * FROM tokens WHERE token_hash = ? AND revoked_at IS NULL",
            (_hash_token(token),),
        ).fetchone()
        if row is None:
            return None
        self._conn.execute(
            "UPDATE tokens SET last_used_at = ? WHERE id = ?",
            (_now_ms(), row["id"]),
        )
        self._conn.commit()
        record = self.get_token(str(row["id"]))
        if record.subject_type == "team":
            return HostedPrincipal(token=record, team_id=record.subject_id)
        repo = self.get_repo(record.subject_id)
        return HostedPrincipal(token=record, team_id=repo.team_id, repo_id=repo.id)

    def register_repo(self, registration: RepoRegistration) -> HostedRepo:
        team = self.get_team(registration.team_slug)
        root = registration.local_path.resolve()
        if not root.is_dir():
            raise ValueError(f"repo path does not exist: {root}")
        now = _now_ms()
        existing = self._conn.execute(
            "SELECT id FROM repos WHERE team_id = ? AND name = ?",
            (team.id, registration.name),
        ).fetchone()
        if existing:
            repo_id = str(existing["id"])
            repo = self.get_repo(repo_id)
            self._conn.execute(
                """
                UPDATE repos
                SET local_path = ?, provider = ?, provider_repo = ?, default_branch = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    str(root),
                    registration.provider,
                    registration.provider_repo,
                    registration.default_branch,
                    now,
                    repo_id,
                ),
            )
            self._conn.commit()
            return self.get_repo(repo.id)
        repo_id = f"repo_{uuid.uuid4().hex}"
        graph_db_path = self.db_path.parent / "graphs" / f"{repo_id}.db"
        graph_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn.execute(
            """
            INSERT INTO repos
                (id, team_id, name, local_path, graph_db_path, provider, provider_repo,
                 default_branch, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repo_id,
                team.id,
                registration.name,
                str(root),
                str(graph_db_path),
                registration.provider,
                registration.provider_repo,
                registration.default_branch,
                now,
                now,
            ),
        )
        self._conn.commit()
        return self.get_repo(repo_id)

    def get_repo(self, repo_id_or_name: str) -> HostedRepo:
        row = self._conn.execute(
            "SELECT * FROM repos WHERE id = ? OR name = ?",
            (repo_id_or_name, repo_id_or_name),
        ).fetchone()
        if row is None:
            raise KeyError(f"repo not found: {repo_id_or_name}")
        return HostedRepo.model_validate(_row_to_dict(row))

    def list_repos(self, team_id: str | None = None) -> list[HostedRepo]:
        if team_id:
            rows = self._conn.execute(
                "SELECT * FROM repos WHERE team_id = ? ORDER BY created_at ASC",
                (team_id,),
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM repos ORDER BY created_at ASC").fetchall()
        return [HostedRepo.model_validate(_row_to_dict(row)) for row in rows]

    def repo_accessible(self, repo: HostedRepo, principal: HostedPrincipal) -> bool:
        if principal.token.subject_type == "team":
            return principal.team_id == repo.team_id
        return principal.repo_id == repo.id

    def record_sync_event(
        self,
        *,
        repo_id: str,
        status: str,
        message: str,
        parsed: int = 0,
        skipped: int = 0,
        errors: int = 0,
        duration_ms: int = 0,
        commit_sha: str | None = None,
    ) -> HostedSyncEvent:
        event_id = f"sync_{uuid.uuid4().hex}"
        now = _now_ms()
        self._conn.execute(
            """
            INSERT INTO sync_events
                (id, repo_id, status, message, parsed, skipped, errors, duration_ms,
                 commit_sha, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                repo_id,
                status,
                message,
                parsed,
                skipped,
                errors,
                duration_ms,
                commit_sha,
                now,
            ),
        )
        self._conn.execute(
            """
            UPDATE repos
            SET last_sync_status = ?, last_error = ?, last_indexed_at = ?,
                last_commit_sha = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                None if status == "success" else message,
                now if status == "success" else None,
                commit_sha,
                now,
                repo_id,
            ),
        )
        self._conn.commit()
        return self.get_sync_event(event_id)

    def get_sync_event(self, event_id: str) -> HostedSyncEvent:
        row = self._conn.execute("SELECT * FROM sync_events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(f"sync event not found: {event_id}")
        return HostedSyncEvent.model_validate(_row_to_dict(row))

    def list_sync_events(self, repo_id: str, limit: int = 20) -> list[HostedSyncEvent]:
        rows = self._conn.execute(
            """
            SELECT * FROM sync_events
            WHERE repo_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (repo_id, limit),
        ).fetchall()
        return [HostedSyncEvent.model_validate(_row_to_dict(row)) for row in rows]

    def sync_repo(self, repo_id_or_name: str) -> SyncResult:
        repo = self.get_repo(repo_id_or_name)
        root = Path(repo.local_path)
        start = time.monotonic()
        commit_sha = _commit_sha(root)
        try:
            if not root.is_dir():
                raise ValueError(f"repo path does not exist: {root}")
            graph_db = Path(repo.graph_db_path)
            graph_db.parent.mkdir(parents=True, exist_ok=True)
            config = CodeAtlasConfig.find_and_load(root)
            config.graph.db_path = graph_db
            store = GraphStore(graph_db)
            try:
                indexer = RepoIndexer(config, store)
                stats = indexer.index_full(resolve=True)
            finally:
                store.close()
            event = self.record_sync_event(
                repo_id=repo.id,
                status="success",
                message="indexed repo",
                parsed=int(stats.get("parsed", 0)),
                skipped=int(stats.get("skipped", 0)),
                errors=int(stats.get("errors", 0)),
                duration_ms=int((time.monotonic() - start) * 1000),
                commit_sha=commit_sha,
            )
        except Exception as exc:
            event = self.record_sync_event(
                repo_id=repo.id,
                status="error",
                message=str(exc),
                duration_ms=int((time.monotonic() - start) * 1000),
                commit_sha=commit_sha,
            )
            raise RuntimeError(str(exc)) from exc
        return SyncResult(repo=self.get_repo(repo.id), event=event)

    def repo_stats(self, repo_id_or_name: str) -> dict[str, object]:
        repo = self.get_repo(repo_id_or_name)
        graph_db = Path(repo.graph_db_path)
        if not graph_db.is_file():
            return {
                "files": 0,
                "symbols": 0,
                "relationships": 0,
                "languages": {},
                "kinds": {},
            }
        store = GraphStore(graph_db)
        try:
            base = store.get_stats()
            return {
                "files": base["files"],
                "symbols": base["symbols"],
                "relationships": base["relationships"],
                "languages": store.get_language_breakdown(),
                "kinds": store.get_kind_breakdown(),
            }
        finally:
            store.close()
