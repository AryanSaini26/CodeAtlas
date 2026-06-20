"""Local-dev hosted control plane for CodeAtlas.

This module intentionally keeps the first hosted MVP dependency-light: SQLite
for metadata, per-repo graph DB paths for isolation, and hashed bearer tokens
for demo-ready auth without external OAuth credentials.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer

TokenSubject = Literal["team", "repo"]

# Repo sync lifecycle. ``never`` is the initial state; ``pending`` once a job is
# queued; ``cloning``/``indexing`` while the worker runs; ``ready`` on success
# and ``failed`` (with ``last_error`` populated) on any error.
SyncStatus = Literal["never", "pending", "cloning", "indexing", "ready", "failed"]
IN_PROGRESS_SYNC_STATUSES = frozenset({"pending", "cloning", "indexing"})

# scrypt work factors. These are salted and memory-hard, unlike a bare SHA-256,
# so a leaked token table cannot be brute-forced with a fast GPU hash. stdlib
# scrypt keeps the hosted control plane dependency-light (no bcrypt/argon2 wheel).
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
# maxmem must exceed 128 * N * r * p bytes (~16 MiB here); give scrypt headroom.
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def _now_ms() -> int:
    return int(time.time() * 1000)


def _hash_token(token: str, *, salt: bytes | None = None) -> str:
    """Return a salted scrypt hash encoded as ``scrypt$N$r$p$salt$digest``."""
    salt = salt if salt is not None else secrets.token_bytes(16)
    derived = hashlib.scrypt(
        token.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def _verify_token_hash(token: str, encoded: str) -> bool:
    """Constant-time verify a token against a stored ``scrypt$...`` hash."""
    parts = encoded.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = base64.b64decode(parts[4])
        expected = base64.b64decode(parts[5])
    except (ValueError, base64.binascii.Error):  # type: ignore[attr-defined]
        return False
    derived = hashlib.scrypt(
        token.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=len(expected),
        maxmem=_SCRYPT_MAXMEM,
    )
    return hmac.compare_digest(derived, expected)


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
    provider_repo_id: str | None = None
    provider_installation_id: str | None = None
    default_branch: str | None = None
    clone_url: str | None = None
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
    delivery_id: str | None = None
    created_at: int


class GitHubInstallation(BaseModel):
    id: str
    installation_id: str
    team_id: str
    account_login: str
    account_type: str
    account_id: str | None = None
    app_slug: str | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)
    created_at: int
    updated_at: int


class GitHubRepository(BaseModel):
    id: str
    installation_id: str
    provider_repo_id: str
    full_name: str
    name: str
    owner: str
    private: bool = False
    default_branch: str | None = None
    clone_url: str | None = None
    local_path: str | None = None
    activated_repo_id: str | None = None
    last_webhook_delivery_id: str | None = None
    last_webhook_event: str | None = None
    created_at: int
    updated_at: int


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


class GitHubCheckoutResult(BaseModel):
    repository: GitHubRepository
    local_path: str
    action: str


@dataclass(frozen=True)
class RepoRegistration:
    team_slug: str
    name: str
    local_path: Path
    provider: str = "local"
    provider_repo: str | None = None
    provider_repo_id: str | None = None
    provider_installation_id: str | None = None
    default_branch: str | None = None
    clone_url: str | None = None


class HostedStore:
    """SQLite metadata store for local hosted-MVP demos."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # The background sync worker opens its own connection to the same file;
        # a busy timeout lets writers wait out a transient lock instead of
        # raising "database is locked".
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        if column not in {str(row["name"]) for row in rows}:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

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
                provider_repo_id TEXT,
                provider_installation_id TEXT,
                default_branch TEXT,
                clone_url TEXT,
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
                delivery_id TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS github_installations (
                id TEXT PRIMARY KEY,
                installation_id TEXT NOT NULL UNIQUE,
                team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                account_login TEXT NOT NULL,
                account_type TEXT NOT NULL,
                account_id TEXT,
                app_slug TEXT,
                permissions TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS github_repositories (
                id TEXT PRIMARY KEY,
                installation_id TEXT NOT NULL REFERENCES github_installations(id) ON DELETE CASCADE,
                provider_repo_id TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                private INTEGER NOT NULL DEFAULT 0,
                default_branch TEXT,
                clone_url TEXT,
                local_path TEXT,
                activated_repo_id TEXT REFERENCES repos(id) ON DELETE SET NULL,
                last_webhook_delivery_id TEXT,
                last_webhook_event TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_repos_team ON repos(team_id);
            CREATE INDEX IF NOT EXISTS idx_repos_provider_id ON repos(provider_repo_id);
            CREATE INDEX IF NOT EXISTS idx_tokens_prefix ON tokens(prefix);
            CREATE INDEX IF NOT EXISTS idx_sync_events_repo_created
                ON sync_events(repo_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sync_events_delivery
                ON sync_events(repo_id, delivery_id);
            CREATE TABLE IF NOT EXISTS repo_evals (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
                summary TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_github_repos_installation
                ON github_repositories(installation_id);
            CREATE INDEX IF NOT EXISTS idx_repo_evals_repo
                ON repo_evals(repo_id, created_at DESC);
            """
        )
        self._ensure_column("repos", "provider_repo_id", "provider_repo_id TEXT")
        self._ensure_column("repos", "provider_installation_id", "provider_installation_id TEXT")
        self._ensure_column("repos", "clone_url", "clone_url TEXT")
        self._ensure_column("sync_events", "delivery_id", "delivery_id TEXT")
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

    def provision_github_login(
        self,
        *,
        github_id: str,
        login: str,
        email: str | None = None,
        name: str | None = None,
    ) -> BootstrapResult:
        """Idempotently create a user + team for a GitHub OAuth sign-in and issue
        a fresh team token. Each login mints a new token (old ones stay valid
        until revoked) since stored hashes can't be reversed to re-show a token.
        """
        now = _now_ms()
        safe_login = login.strip().lower()
        resolved_email = email or f"{github_id}+{safe_login}@users.noreply.github.com"
        resolved_name = name or login
        user_id = self._upsert_user(email=resolved_email, name=resolved_name, created_at=now)
        team_id = self._upsert_team(slug=f"gh-{safe_login}", name=login, created_at=now)
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
            name="github sign-in",
            scopes=["hosted:read", "hosted:write", "repo:sync", "context:read"],
        )
        return BootstrapResult(
            user=self.get_user(user_id),
            team=self.get_team(team_id),
            token=issued.token,
            token_record=issued.token_record,
        )

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
        # Salted scrypt hashes are not directly queryable, so candidates are
        # narrowed by the public prefix and then verified in constant time.
        prefix = token[:12]
        rows = self._conn.execute(
            "SELECT * FROM tokens WHERE prefix = ? AND revoked_at IS NULL",
            (prefix,),
        ).fetchall()
        row = next(
            (
                candidate
                for candidate in rows
                if _verify_token_hash(token, str(candidate["token_hash"]))
            ),
            None,
        )
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
                SET local_path = ?, provider = ?, provider_repo = ?, provider_repo_id = ?,
                    provider_installation_id = ?, default_branch = ?, clone_url = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(root),
                    registration.provider,
                    registration.provider_repo,
                    registration.provider_repo_id,
                    registration.provider_installation_id,
                    registration.default_branch,
                    registration.clone_url,
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
                 provider_repo_id, provider_installation_id, default_branch, clone_url,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repo_id,
                team.id,
                registration.name,
                str(root),
                str(graph_db_path),
                registration.provider,
                registration.provider_repo,
                registration.provider_repo_id,
                registration.provider_installation_id,
                registration.default_branch,
                registration.clone_url,
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

    def upsert_github_installation(
        self,
        *,
        team_slug: str,
        installation_id: str,
        account_login: str,
        account_type: str,
        account_id: str | None = None,
        app_slug: str | None = None,
        permissions: dict[str, Any] | None = None,
    ) -> GitHubInstallation:
        team = self.get_team(team_slug)
        now = _now_ms()
        existing = self._conn.execute(
            "SELECT id FROM github_installations WHERE installation_id = ?",
            (installation_id,),
        ).fetchone()
        if existing:
            installation_pk = str(existing["id"])
            self._conn.execute(
                """
                UPDATE github_installations
                SET team_id = ?, account_login = ?, account_type = ?, account_id = ?,
                    app_slug = ?, permissions = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    team.id,
                    account_login,
                    account_type,
                    account_id,
                    app_slug,
                    json.dumps(permissions or {}, sort_keys=True),
                    now,
                    installation_pk,
                ),
            )
        else:
            installation_pk = f"ghinst_{uuid.uuid4().hex}"
            self._conn.execute(
                """
                INSERT INTO github_installations
                    (id, installation_id, team_id, account_login, account_type,
                     account_id, app_slug, permissions, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    installation_pk,
                    installation_id,
                    team.id,
                    account_login,
                    account_type,
                    account_id,
                    app_slug,
                    json.dumps(permissions or {}, sort_keys=True),
                    now,
                    now,
                ),
            )
        self._conn.commit()
        return self.get_github_installation(installation_pk)

    def _github_installation_from_row(self, row: sqlite3.Row) -> GitHubInstallation:
        data = _row_to_dict(row)
        data["permissions"] = json.loads(str(data["permissions"] or "{}"))
        return GitHubInstallation.model_validate(data)

    def get_github_installation(self, installation_id_or_pk: str) -> GitHubInstallation:
        row = self._conn.execute(
            """
            SELECT * FROM github_installations
            WHERE id = ? OR installation_id = ?
            """,
            (installation_id_or_pk, installation_id_or_pk),
        ).fetchone()
        if row is None:
            raise KeyError(f"github installation not found: {installation_id_or_pk}")
        return self._github_installation_from_row(row)

    def list_github_installations(self, team_id: str | None = None) -> list[GitHubInstallation]:
        if team_id:
            rows = self._conn.execute(
                """
                SELECT * FROM github_installations
                WHERE team_id = ?
                ORDER BY updated_at DESC
                """,
                (team_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM github_installations ORDER BY updated_at DESC"
            ).fetchall()
        return [self._github_installation_from_row(row) for row in rows]

    def upsert_github_repository(
        self,
        *,
        installation_id: str,
        provider_repo_id: str,
        full_name: str,
        name: str,
        owner: str,
        private: bool = False,
        default_branch: str | None = None,
        clone_url: str | None = None,
        local_path: str | None = None,
    ) -> GitHubRepository:
        installation = self.get_github_installation(installation_id)
        now = _now_ms()
        existing = self._conn.execute(
            "SELECT id FROM github_repositories WHERE provider_repo_id = ?",
            (provider_repo_id,),
        ).fetchone()
        if existing:
            repo_pk = str(existing["id"])
            self._conn.execute(
                """
                UPDATE github_repositories
                SET installation_id = ?, full_name = ?, name = ?, owner = ?, private = ?,
                    default_branch = ?, clone_url = ?, local_path = COALESCE(?, local_path),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    installation.id,
                    full_name,
                    name,
                    owner,
                    int(private),
                    default_branch,
                    clone_url,
                    local_path,
                    now,
                    repo_pk,
                ),
            )
        else:
            repo_pk = f"ghrepo_{uuid.uuid4().hex}"
            self._conn.execute(
                """
                INSERT INTO github_repositories
                    (id, installation_id, provider_repo_id, full_name, name, owner,
                     private, default_branch, clone_url, local_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repo_pk,
                    installation.id,
                    provider_repo_id,
                    full_name,
                    name,
                    owner,
                    int(private),
                    default_branch,
                    clone_url,
                    local_path,
                    now,
                    now,
                ),
            )
        self._conn.commit()
        return self.get_github_repository(provider_repo_id)

    def _github_repository_from_row(self, row: sqlite3.Row) -> GitHubRepository:
        data = _row_to_dict(row)
        data["private"] = bool(data["private"])
        return GitHubRepository.model_validate(data)

    def get_github_repository(self, provider_repo_id_or_full_name: str) -> GitHubRepository:
        row = self._conn.execute(
            """
            SELECT * FROM github_repositories
            WHERE id = ? OR provider_repo_id = ? OR full_name = ?
            """,
            (
                provider_repo_id_or_full_name,
                provider_repo_id_or_full_name,
                provider_repo_id_or_full_name,
            ),
        ).fetchone()
        if row is None:
            raise KeyError(f"github repository not found: {provider_repo_id_or_full_name}")
        return self._github_repository_from_row(row)

    def list_github_repositories(
        self,
        installation_id: str | None = None,
    ) -> list[GitHubRepository]:
        if installation_id:
            installation = self.get_github_installation(installation_id)
            rows = self._conn.execute(
                """
                SELECT * FROM github_repositories
                WHERE installation_id = ?
                ORDER BY full_name ASC
                """,
                (installation.id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM github_repositories ORDER BY full_name ASC"
            ).fetchall()
        return [self._github_repository_from_row(row) for row in rows]

    def activate_github_repository(
        self,
        provider_repo_id: str,
        *,
        local_path: Path | str | None = None,
        hosted_name: str | None = None,
    ) -> HostedRepo:
        github_repo = self.get_github_repository(provider_repo_id)
        installation = self.get_github_installation(github_repo.installation_id)
        if local_path is None and github_repo.local_path is None:
            checkout = self.clone_or_update_github_repository(provider_repo_id)
            resolved_local_path = checkout.local_path
            github_repo = checkout.repository
        else:
            resolved_local_path = str(local_path or github_repo.local_path or "")
        if not resolved_local_path:
            raise ValueError(
                "GitHub repo activation needs a local_path or clone_url for hosted checkout"
            )
        repo = self.register_repo(
            RepoRegistration(
                team_slug=self.get_team(installation.team_id).slug,
                name=hosted_name or github_repo.full_name,
                local_path=Path(resolved_local_path),
                provider="github",
                provider_repo=github_repo.full_name,
                provider_repo_id=github_repo.provider_repo_id,
                provider_installation_id=installation.installation_id,
                default_branch=github_repo.default_branch,
                clone_url=github_repo.clone_url,
            )
        )
        now = _now_ms()
        self._conn.execute(
            """
            UPDATE github_repositories
            SET activated_repo_id = ?, local_path = ?, updated_at = ?
            WHERE provider_repo_id = ?
            """,
            (repo.id, resolved_local_path, now, github_repo.provider_repo_id),
        )
        self._conn.commit()
        return self.get_repo(repo.id)

    def clone_or_update_github_repository(
        self,
        provider_repo_id: str,
        *,
        checkout_root: Path | str | None = None,
    ) -> GitHubCheckoutResult:
        github_repo = self.get_github_repository(provider_repo_id)
        if not github_repo.clone_url:
            raise ValueError(f"github repository {github_repo.full_name} has no clone_url")
        root = (
            Path(checkout_root) if checkout_root is not None else self.db_path.parent / "checkouts"
        )
        target = root / provider_repo_id
        root.mkdir(parents=True, exist_ok=True)
        action = "updated"
        if (target / ".git").is_dir():
            self._run_git(["fetch", "--all", "--prune"], cwd=target)
            if github_repo.default_branch:
                self._run_git(["checkout", github_repo.default_branch], cwd=target)
            self._run_git(["pull", "--ff-only"], cwd=target)
        else:
            action = "cloned"
            self._run_git(["clone", "--depth", "1", github_repo.clone_url, str(target)], cwd=root)
            if github_repo.default_branch:
                self._run_git(["checkout", github_repo.default_branch], cwd=target)
        now = _now_ms()
        self._conn.execute(
            """
            UPDATE github_repositories
            SET local_path = ?, updated_at = ?
            WHERE provider_repo_id = ?
            """,
            (str(target), now, provider_repo_id),
        )
        self._conn.commit()
        return GitHubCheckoutResult(
            repository=self.get_github_repository(provider_repo_id),
            local_path=str(target),
            action=action,
        )

    def sync_github_repository(self, provider_repo_id: str) -> SyncResult:
        hosted_repo = self.get_repo_by_provider_id(provider_repo_id)
        if hosted_repo is None:
            hosted_repo = self.activate_github_repository(provider_repo_id)
        else:
            self.clone_or_update_github_repository(provider_repo_id)
            hosted_repo = self.activate_github_repository(provider_repo_id)
        return self.sync_repo(hosted_repo.id)

    def _run_git(self, args: list[str], *, cwd: Path) -> None:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"git {' '.join(args)} failed: {message}")

    def get_repo_by_provider_id(self, provider_repo_id: str) -> HostedRepo | None:
        row = self._conn.execute(
            "SELECT * FROM repos WHERE provider_repo_id = ?",
            (provider_repo_id,),
        ).fetchone()
        if row is None:
            return None
        return HostedRepo.model_validate(_row_to_dict(row))

    def update_github_webhook_delivery(
        self,
        *,
        provider_repo_id: str,
        delivery_id: str | None,
        event: str,
    ) -> None:
        self._conn.execute(
            """
            UPDATE github_repositories
            SET last_webhook_delivery_id = ?, last_webhook_event = ?, updated_at = ?
            WHERE provider_repo_id = ?
            """,
            (delivery_id, event, _now_ms(), provider_repo_id),
        )
        self._conn.commit()

    def delivery_already_processed(self, repo_id: str, delivery_id: str | None) -> bool:
        """True if a sync event already exists for this repo + GitHub delivery id.

        GitHub redelivers webhooks on timeout/error, so the ingestion handler
        must no-op on a duplicate ``X-GitHub-Delivery`` instead of racing a
        second sync against the same per-repo graph DB.
        """
        if not delivery_id:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM sync_events WHERE repo_id = ? AND delivery_id = ? LIMIT 1",
            (repo_id, delivery_id),
        ).fetchone()
        return row is not None

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
        delivery_id: str | None = None,
    ) -> HostedSyncEvent:
        event_id = f"sync_{uuid.uuid4().hex}"
        now = _now_ms()
        self._conn.execute(
            """
            INSERT INTO sync_events
                (id, repo_id, status, message, parsed, skipped, errors, duration_ms,
                 commit_sha, delivery_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                delivery_id,
                now,
            ),
        )
        # sync_events.status stays "success"/"error" (the run outcome); the repo
        # lifecycle field maps those to the terminal states "ready"/"failed".
        succeeded = status == "success"
        self._conn.execute(
            """
            UPDATE repos
            SET last_sync_status = ?, last_error = ?, last_indexed_at = ?,
                last_commit_sha = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                "ready" if succeeded else "failed",
                None if succeeded else message,
                now if succeeded else None,
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

    def set_sync_status(
        self,
        repo_id_or_name: str,
        status: SyncStatus,
        *,
        error: str | None = None,
    ) -> HostedRepo:
        """Set the repo lifecycle status (used by the background sync worker)."""
        repo = self.get_repo(repo_id_or_name)
        self._conn.execute(
            "UPDATE repos SET last_sync_status = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (status, error, _now_ms(), repo.id),
        )
        self._conn.commit()
        return self.get_repo(repo.id)

    def run_sync_pipeline(
        self,
        repo_id_or_name: str,
        *,
        delivery_id: str | None = None,
        github_provider_repo_id: str | None = None,
    ) -> SyncResult:
        """Walk a repo through clone -> index, updating its lifecycle status.

        Used by both the synchronous "sync now" routes and the background
        worker. When ``github_provider_repo_id`` points at a repo with a
        ``clone_url`` the working tree is refreshed before indexing, so a push
        webhook indexes the just-pushed commit rather than a stale checkout.
        """
        repo = self.get_repo(repo_id_or_name)
        try:
            if github_provider_repo_id:
                github_repo = self.get_github_repository(github_provider_repo_id)
                if github_repo.clone_url:
                    self.set_sync_status(repo.id, "cloning")
                    self.clone_or_update_github_repository(github_provider_repo_id)
            self.set_sync_status(repo.id, "indexing")
        except Exception as exc:
            # Surface checkout failures the same way index failures are surfaced.
            self.record_sync_event(
                repo_id=repo.id,
                status="error",
                message=str(exc),
                delivery_id=delivery_id,
            )
            raise RuntimeError(str(exc)) from exc
        return self.sync_repo(repo.id, delivery_id=delivery_id)

    def sync_repo(self, repo_id_or_name: str, *, delivery_id: str | None = None) -> SyncResult:
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
                delivery_id=delivery_id,
            )
        except Exception as exc:
            event = self.record_sync_event(
                repo_id=repo.id,
                status="error",
                message=str(exc),
                duration_ms=int((time.monotonic() - start) * 1000),
                commit_sha=commit_sha,
                delivery_id=delivery_id,
            )
            raise RuntimeError(str(exc)) from exc
        return SyncResult(repo=self.get_repo(repo.id), event=event)

    def seed_demo_repo(
        self,
        clone_url: str,
        *,
        name: str | None = None,
        team_slug: str = "demo",
    ) -> tuple[HostedRepo, str]:
        """Clone + index a repo for the public read-only demo and issue a token.

        Returns the repo and a *repo-scoped* token (subject_type='repo') so the
        public token can only read this one repo's context — never other repos or
        team-management routes.
        """
        self.create_team(slug=team_slug, name="Stratum Demo")
        repo_name = name or clone_url.rstrip("/").split("/")[-1].removesuffix(".git")
        target = self.db_path.parent / "demo-checkouts" / repo_name
        target.parent.mkdir(parents=True, exist_ok=True)
        if (target / ".git").is_dir():
            self._run_git(["fetch", "--all", "--prune"], cwd=target)
            self._run_git(["pull", "--ff-only"], cwd=target)
        else:
            self._run_git(["clone", "--depth", "1", clone_url, str(target)], cwd=target.parent)
        repo = self.register_repo(
            RepoRegistration(
                team_slug=team_slug,
                name=repo_name,
                local_path=target,
                provider="local",
                clone_url=clone_url,
            )
        )
        self.run_sync_pipeline(repo.id)
        issued = self.create_token(
            subject_type="repo",
            subject_id=repo.id,
            name="public demo (read-only)",
            scopes=["context:read"],
        )
        return self.get_repo(repo.id), issued.token

    def metrics(self) -> dict[str, Any]:
        """Crude signup/activation metrics for tracking from day one.

        Activation = a repo that has had at least one successful sync.
        """

        def count(sql: str) -> int:
            return int(self._conn.execute(sql).fetchone()[0])

        users = count("SELECT COUNT(*) FROM users")
        repos = count("SELECT COUNT(*) FROM repos")
        activated = count(
            "SELECT COUNT(DISTINCT repo_id) FROM sync_events WHERE status = 'success'"
        )
        return {
            "users": users,
            "teams": count("SELECT COUNT(*) FROM teams"),
            "repos": repos,
            "activated_repos": activated,
            "ready_repos": count("SELECT COUNT(*) FROM repos WHERE last_sync_status = 'ready'"),
            "successful_syncs": count("SELECT COUNT(*) FROM sync_events WHERE status = 'success'"),
            "failed_syncs": count("SELECT COUNT(*) FROM sync_events WHERE status = 'error'"),
            "github_installations": count("SELECT COUNT(*) FROM github_installations"),
            "activation_rate": round(activated / repos, 4) if repos else 0.0,
        }

    def record_repo_eval(self, repo_id: str, summary: dict[str, Any]) -> dict[str, Any]:
        """Persist the latest retrieval-eval summary for a repo."""
        eval_id = f"eval_{uuid.uuid4().hex}"
        self._conn.execute(
            "INSERT INTO repo_evals (id, repo_id, summary, created_at) VALUES (?, ?, ?, ?)",
            (eval_id, repo_id, json.dumps(summary), _now_ms()),
        )
        self._conn.commit()
        return summary

    def get_latest_repo_eval(self, repo_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT summary FROM repo_evals WHERE repo_id = ? ORDER BY created_at DESC LIMIT 1",
            (repo_id,),
        ).fetchone()
        if row is None:
            return None
        data: dict[str, Any] = json.loads(str(row["summary"]))
        return data

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
