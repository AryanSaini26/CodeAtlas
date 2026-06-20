"""FastAPI routes for the local-dev hosted CodeAtlas control plane."""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from codeatlas.agent_context import build_context_pack
from codeatlas.context_security import scan_context_pack
from codeatlas.data_lineage import build_lineage_graph
from codeatlas.github_app import (
    build_oauth_authorize_url,
    exchange_oauth_code,
    fetch_github_user,
    load_github_app_config,
    parse_webhook_payload,
    process_github_webhook,
    refresh_github_repositories,
    verify_github_signature,
)
from codeatlas.graph.store import GraphStore
from codeatlas.hosted import (
    HostedPrincipal,
    HostedRepo,
    HostedStore,
    RepoRegistration,
)
from codeatlas.hosted_eval import compute_context_savings, run_repo_retrieval_eval
from codeatlas.hosted_worker import SyncJobWorker
from codeatlas.rate_limit import context_rate_limiter, webhook_rate_limiter


class BootstrapRequest(BaseModel):
    email: str = "dev@codeatlas.local"
    name: str = "CodeAtlas Dev"
    team_slug: str = "default"
    team_name: str = "Default Team"


class TeamCreateRequest(BaseModel):
    slug: str = Field(min_length=1)
    name: str = Field(min_length=1)


class RepoCreateRequest(BaseModel):
    team_slug: str = "default"
    name: str = Field(min_length=1)
    local_path: str = Field(min_length=1)
    provider: str = "local"
    provider_repo: str | None = None
    provider_repo_id: str | None = None
    provider_installation_id: str | None = None
    default_branch: str | None = None
    clone_url: str | None = None


class TokenCreateRequest(BaseModel):
    name: str = "repo token"
    scopes: list[str] = Field(default_factory=lambda: ["context:read", "repo:sync"])


class GitHubInstallationRequest(BaseModel):
    team_slug: str = "default"
    installation_id: str = Field(min_length=1)
    account_login: str = Field(min_length=1)
    account_type: str = "Organization"
    account_id: str | None = None
    app_slug: str | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)


class GitHubRepositoryRequest(BaseModel):
    installation_id: str = Field(min_length=1)
    provider_repo_id: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    name: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    private: bool = False
    default_branch: str | None = None
    clone_url: str | None = None
    local_path: str | None = None


class GitHubActivateRequest(BaseModel):
    local_path: str | None = Field(default=None, min_length=1)
    hosted_name: str | None = None


class RemoteMCPRequest(BaseModel):
    method: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


def _bearer_token(header: str | None) -> str | None:
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _require_repo_access(
    hosted: HostedStore,
    repo_id: str,
    principal: HostedPrincipal,
) -> HostedRepo:
    try:
        repo = hosted.get_repo(repo_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc
    if not hosted.repo_accessible(repo, principal):
        raise HTTPException(status_code=403, detail={"error": "repo token cannot access repo"})
    return repo


def _validate_repo_audience(repo: HostedRepo, audience: str | None) -> None:
    accepted = {f"repo:{repo.id}", f"repo:{repo.name}"}
    if repo.provider_repo:
        accepted.add(f"repo:{repo.provider_repo}")
    if audience not in accepted:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid or missing Stratum audience",
                "accepted": sorted(accepted),
            },
        )


def build_hosted_router(
    hosted: HostedStore,
    worker: SyncJobWorker | None = None,
) -> APIRouter:
    """Build hosted-MVP API routes.

    ``/dev/bootstrap`` is intentionally open for local demos; every other route
    requires ``Authorization: Bearer <token>``. When ``worker`` is provided,
    push webhooks enqueue sync jobs off the request path instead of indexing
    inline.
    """

    router = APIRouter()
    _webhook_limiter = webhook_rate_limiter()
    _context_limiter = context_rate_limiter()
    # OAuth CSRF states: state -> expiry epoch seconds (in-process, single deploy).
    _oauth_states: dict[str, float] = {}

    def _oauth_redirect_uri(config: Any) -> str:
        base = (config.public_url or "").rstrip("/")
        if not base:
            raise HTTPException(
                status_code=500,
                detail={"error": "STRATUM_PUBLIC_URL must be set for GitHub OAuth"},
            )
        return f"{base}/api/hosted/v1/github/oauth/callback"

    def _enforce_rate_limit(limiter: Any, key: str) -> None:
        if not limiter.allow(key):
            raise HTTPException(
                status_code=429,
                detail={"error": "rate limit exceeded"},
                headers={"Retry-After": str(limiter.retry_after_seconds())},
            )

    def _log_context_query(
        repo_id: str, query: str, pack: dict[str, Any], source: str, started: float
    ) -> None:
        # Audit-log the query for the Context Feed; never fail the request on a log error.
        raw_security = pack.get("security")
        security = raw_security if isinstance(raw_security, dict) else {}
        try:
            hosted.record_context_query(
                repo_id=repo_id,
                query=query,
                mode=str(pack.get("mode_effective") or pack.get("mode") or "pagerank"),
                source=source,
                tokens=int(pack.get("estimated_tokens", 0) or 0),
                result_count=int(pack.get("result_count", 0) or 0),
                latency_ms=int((time.monotonic() - started) * 1000),
                security_status=str(security.get("status", "ok")),
            )
        except Exception:
            pass

    async def principal_dep(
        authorization: str | None = Header(default=None),
    ) -> HostedPrincipal:
        token = _bearer_token(authorization)
        if token is None:
            raise HTTPException(status_code=401, detail={"error": "missing bearer token"})
        principal = hosted.verify_token(token)
        if principal is None:
            raise HTTPException(status_code=401, detail={"error": "invalid bearer token"})
        return principal

    @router.post("/dev/bootstrap")
    async def dev_bootstrap(payload: BootstrapRequest | None = None) -> dict[str, Any]:
        payload = payload or BootstrapRequest()
        result = hosted.bootstrap_dev(
            email=payload.email,
            name=payload.name,
            team_slug=payload.team_slug,
            team_name=payload.team_name,
        )
        return result.model_dump()

    @router.get("/me")
    async def me(principal: HostedPrincipal = Depends(principal_dep)) -> dict[str, Any]:
        return principal.model_dump()

    @router.get("/demo-info")
    async def demo_info() -> dict[str, Any]:
        # Public, opt-in: exposes the read-only demo repo token (set via env after
        # `codeatlas hosted seed-demo`) so visitors can explore without signup.
        token = os.environ.get("STRATUM_DEMO_TOKEN")
        repo_id = os.environ.get("STRATUM_DEMO_REPO_ID")
        if not token or not repo_id:
            return {"enabled": False}
        return {"enabled": True, "token": token, "repo_id": repo_id}

    @router.get("/metrics")
    async def metrics(
        x_stratum_admin: str | None = Header(default=None),
    ) -> dict[str, Any]:
        # Admin-only: disabled unless STRATUM_ADMIN_TOKEN is set, to avoid
        # leaking aggregate usage on a public endpoint.
        admin_token = os.environ.get("STRATUM_ADMIN_TOKEN")
        if not admin_token:
            raise HTTPException(status_code=404, detail={"error": "metrics endpoint disabled"})
        if not x_stratum_admin or not secrets.compare_digest(x_stratum_admin, admin_token):
            raise HTTPException(status_code=401, detail={"error": "admin token required"})
        return hosted.metrics()

    @router.get("/audit")
    async def audit_log(
        limit: int = Query(default=50, ge=1, le=500),
        x_stratum_admin: str | None = Header(default=None),
    ) -> dict[str, Any]:
        # Admin-only, same gating as /metrics — an audit trail shouldn't be public.
        admin_token = os.environ.get("STRATUM_ADMIN_TOKEN")
        if not admin_token:
            raise HTTPException(status_code=404, detail={"error": "audit endpoint disabled"})
        if not x_stratum_admin or not secrets.compare_digest(x_stratum_admin, admin_token):
            raise HTTPException(status_code=401, detail={"error": "admin token required"})
        return {"events": [e.model_dump() for e in hosted.list_audit_events(limit=limit)]}

    @router.get("/teams")
    async def teams(_: HostedPrincipal = Depends(principal_dep)) -> dict[str, Any]:
        return {"teams": [team.model_dump() for team in hosted.list_teams()]}

    @router.post("/teams")
    async def create_team(
        payload: TeamCreateRequest,
        _: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        try:
            team = hosted.create_team(slug=payload.slug, name=payload.name)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        return {"team": team.model_dump()}

    @router.get("/repos")
    async def repos(principal: HostedPrincipal = Depends(principal_dep)) -> dict[str, Any]:
        repo_list = hosted.list_repos(team_id=principal.team_id)
        if principal.repo_id:
            repo_list = [repo for repo in repo_list if repo.id == principal.repo_id]
        return {"repos": [repo.model_dump() for repo in repo_list]}

    @router.post("/repos")
    async def create_repo(
        payload: RepoCreateRequest,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        if principal.token.subject_type != "team":
            raise HTTPException(status_code=403, detail={"error": "team token required"})
        try:
            team = hosted.get_team(payload.team_slug)
            if principal.team_id != team.id:
                raise PermissionError("token cannot access team")
            repo = hosted.register_repo(
                RepoRegistration(
                    team_slug=payload.team_slug,
                    name=payload.name,
                    local_path=Path(payload.local_path),
                    provider=payload.provider,
                    provider_repo=payload.provider_repo,
                    provider_repo_id=payload.provider_repo_id,
                    provider_installation_id=payload.provider_installation_id,
                    default_branch=payload.default_branch,
                    clone_url=payload.clone_url,
                )
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail={"error": str(exc)}) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        return {"repo": repo.model_dump()}

    @router.get("/repos/{repo_id}")
    async def get_repo(
        repo_id: str,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        return {"repo": repo.model_dump()}

    @router.post("/repos/{repo_id}/sync")
    async def sync_repo(
        repo_id: str,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        github_provider_repo_id = repo.provider_repo_id if repo.provider == "github" else None
        try:
            result = hosted.run_sync_pipeline(
                repo.id,
                github_provider_repo_id=github_provider_repo_id,
            )
        except RuntimeError as exc:
            fresh_repo = hosted.get_repo(repo.id)
            events = hosted.list_sync_events(repo.id, limit=1)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": str(exc),
                    "repo": fresh_repo.model_dump(),
                    "event": events[0].model_dump() if events else None,
                },
            ) from exc
        return {"repo": result.repo.model_dump(), "event": result.event.model_dump()}

    @router.get("/repos/{repo_id}/stats")
    async def repo_stats(
        repo_id: str,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        return {"repo": repo.model_dump(), "stats": hosted.repo_stats(repo.id)}

    @router.post("/repos/{repo_id}/eval")
    async def run_repo_eval(
        repo_id: str,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        graph_db = Path(repo.graph_db_path)
        if not graph_db.is_file():
            raise HTTPException(status_code=409, detail={"error": "repo has not been synced"})
        try:
            summary = run_repo_retrieval_eval(graph_db)
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc
        hosted.record_repo_eval(repo.id, summary)
        return {"eval": summary}

    @router.get("/repos/{repo_id}/eval")
    async def latest_repo_eval(
        repo_id: str,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        return {"eval": hosted.get_latest_repo_eval(repo.id)}

    @router.get("/repos/{repo_id}/context-savings")
    async def context_savings(
        repo_id: str,
        q: str = Query(..., min_length=1),
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        _enforce_rate_limit(_context_limiter, f"savings:{principal.token.id}:{repo.id}")
        graph_db = Path(repo.graph_db_path)
        if not graph_db.is_file():
            raise HTTPException(status_code=409, detail={"error": "repo has not been synced"})
        root = Path(repo.local_path)
        if not root.is_dir():
            raise HTTPException(status_code=409, detail={"error": "repo has no local checkout"})
        return {"savings": compute_context_savings(graph_db, root, q)}

    @router.get("/repos/{repo_id}/freshness")
    async def repo_freshness(
        repo_id: str,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        return {"freshness": hosted.repo_freshness(repo.id)}

    @router.get("/repos/{repo_id}/explain")
    async def explain_repo(
        repo_id: str,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        graph_db = Path(repo.graph_db_path)
        if not graph_db.is_file():
            raise HTTPException(status_code=409, detail={"error": "repo has not been synced"})
        from codeatlas.repo_overview import build_repo_explainer

        store = GraphStore(graph_db)
        try:
            return build_repo_explainer(store, repo_name=repo.name)
        finally:
            store.close()

    @router.get("/repos/{repo_id}/context-queries")
    async def context_queries(
        repo_id: str,
        limit: int = Query(default=25, ge=1, le=100),
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        return {
            "queries": [q.model_dump() for q in hosted.list_context_queries(repo.id, limit=limit)]
        }

    @router.get("/repos/{repo_id}/lineage")
    async def repo_lineage(
        repo_id: str,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        root = Path(repo.local_path)
        if not root.is_dir():
            raise HTTPException(status_code=409, detail={"error": "repo has no local checkout"})
        return {"lineage": build_lineage_graph(root)}

    @router.get("/repos/{repo_id}/sync-events")
    async def sync_events(
        repo_id: str,
        limit: int = Query(default=20, ge=1, le=100),
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        events = hosted.list_sync_events(repo.id, limit=limit)
        return {"events": [event.model_dump() for event in events]}

    @router.get("/repos/{repo_id}/context")
    async def repo_context(
        repo_id: str,
        q: str = Query(..., min_length=1),
        budget: int = Query(default=2000, ge=128, le=50000),
        limit: int = Query(default=10, ge=1, le=100),
        mode: Literal["fts", "semantic", "hybrid", "pagerank"] = "pagerank",
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        _enforce_rate_limit(_context_limiter, f"ctx:{principal.token.id}:{repo.id}")
        graph_db = Path(repo.graph_db_path)
        if not graph_db.is_file():
            raise HTTPException(status_code=409, detail={"error": "repo has not been synced"})
        started = time.monotonic()
        store = GraphStore(graph_db)
        try:
            pack = build_context_pack(
                store,
                q,
                budget_tokens=budget,
                limit=limit,
                mode=mode,
            )
            pack["security"] = scan_context_pack(pack)
            _log_context_query(repo.id, q, pack, "context-api", started)
            return pack
        finally:
            store.close()

    @router.post("/repos/{repo_id}/remote-mcp")
    async def remote_mcp(
        repo_id: str,
        payload: RemoteMCPRequest,
        x_stratum_audience: str | None = Header(default=None),
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        _validate_repo_audience(repo, x_stratum_audience)
        _enforce_rate_limit(_context_limiter, f"mcp:{principal.token.id}:{repo.id}")
        graph_db = Path(repo.graph_db_path)
        if not graph_db.is_file():
            raise HTTPException(status_code=409, detail={"error": "repo has not been synced"})

        if payload.method == "tools/call":
            name = payload.params.get("name")
            arguments = payload.params.get("arguments")
            arguments = arguments if isinstance(arguments, dict) else {}
            if name not in {"context", "codeatlas.context", "stratum.context"}:
                raise HTTPException(status_code=400, detail={"error": f"unsupported tool: {name}"})
            q = str(arguments.get("q") or arguments.get("query") or "").strip()
            if not q:
                raise HTTPException(status_code=400, detail={"error": "context query is required"})
            budget = int(arguments.get("budget", 2000))
            mode = str(arguments.get("mode", "pagerank"))
            if mode not in {"fts", "semantic", "hybrid", "pagerank"}:
                raise HTTPException(status_code=400, detail={"error": f"unsupported mode: {mode}"})
            mode_cast = cast(Literal["fts", "semantic", "hybrid", "pagerank"], mode)
            started = time.monotonic()
            store = GraphStore(graph_db)
            try:
                pack = build_context_pack(
                    store,
                    q,
                    budget_tokens=budget,
                    mode=mode_cast,
                )
                pack["security"] = scan_context_pack(pack)
                _log_context_query(repo.id, q, pack, "remote-mcp", started)
            finally:
                store.close()
            return {"jsonrpc": "2.0", "result": pack}

        if payload.method == "resources/read":
            uri = str(payload.params.get("uri") or "")
            if uri != "codeatlas://graph/summary":
                raise HTTPException(
                    status_code=400, detail={"error": f"unsupported resource: {uri}"}
                )
            return {"jsonrpc": "2.0", "result": hosted.repo_stats(repo.id)}

        raise HTTPException(
            status_code=400, detail={"error": f"unsupported method: {payload.method}"}
        )

    @router.post("/repos/{repo_id}/tokens")
    async def repo_token(
        repo_id: str,
        payload: TokenCreateRequest,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        if principal.token.subject_type != "team":
            raise HTTPException(status_code=403, detail={"error": "team token required"})
        issued = hosted.create_token(
            subject_type="repo",
            subject_id=repo.id,
            name=payload.name,
            scopes=payload.scopes,
        )
        return issued.model_dump()

    @router.get("/repos/{repo_id}/connection")
    async def connection(
        repo_id: str,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        repo = _require_repo_access(hosted, repo_id, principal)
        return {
            "repo": repo.model_dump(),
            "status": "hosted_context_api_ready",
            "context_endpoint": f"/api/hosted/v1/repos/{repo.id}/context",
            "remote_mcp_endpoint": f"/api/hosted/v1/repos/{repo.id}/remote-mcp",
            "auth_header": "Authorization: Bearer <repo-or-team-token>",
            "audience_header": f"X-Stratum-Audience: repo:{repo.id}",
            "mcp_note": (
                "This hosted endpoint accepts a small MCP-compatible JSON shape for "
                "context tools and graph summary resources. Full streamable MCP "
                "transport can layer on top of the same repo-scoped auth model."
            ),
            "local_mcp_config": {
                "mcpServers": {
                    "codeatlas": {
                        "command": "codeatlas",
                        "args": ["serve", "--db", repo.graph_db_path],
                    }
                }
            },
        }

    @router.get("/github/app")
    async def github_app() -> dict[str, Any]:
        config = load_github_app_config()
        return {
            "brand": "Stratum",
            "engine": "CodeAtlas",
            "configured": config.configured,
            "oauth_configured": config.oauth_configured,
            "webhook_configured": config.webhook_configured,
            "app_id": config.app_id,
            "client_id": config.client_id,
            "public_url": config.public_url,
            "setup_url": (
                f"{config.public_url.rstrip('/')}/api/hosted/v1/github/setup"
                if config.public_url
                else None
            ),
            "repo_listing_source": (
                "fixture"
                if config.repos_fixture_path
                else "github_api"
                if (config.installation_token or config.configured)
                else "store"
            ),
        }

    @router.get("/github/setup")
    async def github_setup_callback(
        installation_id: str = Query(..., min_length=1),
        setup_action: str | None = None,
        team_slug: str = "default",
    ) -> dict[str, Any]:
        hosted.create_team(slug=team_slug, name="Default Team")
        installation = hosted.upsert_github_installation(
            team_slug=team_slug,
            installation_id=installation_id,
            account_login="pending",
            account_type="Organization",
            app_slug="stratum",
        )
        return {
            "status": "installation_registered",
            "setup_action": setup_action,
            "installation": installation.model_dump(),
            "next": "Authenticate with a team token, then refresh repos for this installation.",
        }

    @router.post("/github/installations")
    async def register_github_installation(
        payload: GitHubInstallationRequest,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        if principal.token.subject_type != "team":
            raise HTTPException(status_code=403, detail={"error": "team token required"})
        team = hosted.get_team(payload.team_slug)
        if principal.team_id != team.id:
            raise HTTPException(status_code=403, detail={"error": "token cannot access team"})
        installation = hosted.upsert_github_installation(
            team_slug=payload.team_slug,
            installation_id=payload.installation_id,
            account_login=payload.account_login,
            account_type=payload.account_type,
            account_id=payload.account_id,
            app_slug=payload.app_slug,
            permissions=payload.permissions,
        )
        return {"installation": installation.model_dump()}

    @router.get("/github/installations")
    async def github_installations(
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        return {
            "installations": [
                installation.model_dump()
                for installation in hosted.list_github_installations(team_id=principal.team_id)
            ]
        }

    @router.post("/github/installations/{installation_id}/repos")
    async def register_github_repo(
        installation_id: str,
        payload: GitHubRepositoryRequest,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        installation = hosted.get_github_installation(installation_id)
        if principal.team_id != installation.team_id:
            raise HTTPException(
                status_code=403, detail={"error": "token cannot access installation"}
            )
        repo = hosted.upsert_github_repository(
            installation_id=payload.installation_id,
            provider_repo_id=payload.provider_repo_id,
            full_name=payload.full_name,
            name=payload.name,
            owner=payload.owner,
            private=payload.private,
            default_branch=payload.default_branch,
            clone_url=payload.clone_url,
            local_path=payload.local_path,
        )
        return {"repository": repo.model_dump()}

    @router.get("/github/installations/{installation_id}/repos")
    async def github_repos(
        installation_id: str,
        refresh: bool = Query(default=False),
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        installation = hosted.get_github_installation(installation_id)
        if principal.team_id != installation.team_id:
            raise HTTPException(
                status_code=403, detail={"error": "token cannot access installation"}
            )
        source = "store"
        if refresh:
            try:
                listing = refresh_github_repositories(
                    hosted,
                    installation_id=installation.installation_id,
                    config=load_github_app_config(),
                )
            except Exception as exc:
                raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
            source = listing.source
        repos = hosted.list_github_repositories(installation_id=installation.id)
        return {"source": source, "repositories": [repo.model_dump() for repo in repos]}

    @router.post("/github/repos/{provider_repo_id}/activate")
    async def activate_github_repo(
        provider_repo_id: str,
        payload: GitHubActivateRequest,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        github_repo = hosted.get_github_repository(provider_repo_id)
        installation = hosted.get_github_installation(github_repo.installation_id)
        if principal.token.subject_type != "team":
            raise HTTPException(status_code=403, detail={"error": "team token required"})
        if principal.team_id != installation.team_id:
            raise HTTPException(status_code=403, detail={"error": "token cannot access repo"})
        try:
            repo = hosted.activate_github_repository(
                provider_repo_id,
                local_path=payload.local_path,
                hosted_name=payload.hosted_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        return {"repo": repo.model_dump()}

    @router.post("/github/repos/{provider_repo_id}/sync")
    async def sync_github_repo(
        provider_repo_id: str,
        principal: HostedPrincipal = Depends(principal_dep),
    ) -> dict[str, Any]:
        github_repo = hosted.get_github_repository(provider_repo_id)
        installation = hosted.get_github_installation(github_repo.installation_id)
        if principal.token.subject_type != "team":
            raise HTTPException(status_code=403, detail={"error": "team token required"})
        if principal.team_id != installation.team_id:
            raise HTTPException(status_code=403, detail={"error": "token cannot access repo"})
        try:
            result = hosted.sync_github_repository(provider_repo_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        return {"repo": result.repo.model_dump(), "event": result.event.model_dump()}

    @router.get("/github/oauth/login")
    async def github_oauth_login() -> RedirectResponse:
        config = load_github_app_config()
        if not config.oauth_configured:
            raise HTTPException(status_code=400, detail={"error": "GitHub OAuth is not configured"})
        # Drop expired states so the in-memory store can't grow unbounded.
        now = time.time()
        for stale in [s for s, exp in _oauth_states.items() if exp < now]:
            _oauth_states.pop(stale, None)
        state = secrets.token_urlsafe(24)
        _oauth_states[state] = now + 600
        url = build_oauth_authorize_url(
            config, state=state, redirect_uri=_oauth_redirect_uri(config)
        )
        return RedirectResponse(url, status_code=307)

    @router.get("/github/oauth/callback")
    async def github_oauth_callback(
        code: str | None = None,
        state: str | None = None,
    ) -> RedirectResponse:
        config = load_github_app_config()
        if not config.oauth_configured:
            raise HTTPException(status_code=400, detail={"error": "GitHub OAuth is not configured"})
        if not code or not state:
            raise HTTPException(status_code=400, detail={"error": "missing code or state"})
        expiry = _oauth_states.pop(state, None)
        if expiry is None or expiry < time.time():
            raise HTTPException(status_code=401, detail={"error": "invalid or expired state"})
        try:
            access_token = exchange_oauth_code(
                config, code=code, redirect_uri=_oauth_redirect_uri(config)
            )
            gh_user = fetch_github_user(access_token, api_base=config.api_base)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        result = hosted.provision_github_login(
            github_id=gh_user.github_id,
            login=gh_user.login,
            email=gh_user.email,
            name=gh_user.name,
        )
        # Hand the token to the SPA via the URL fragment (never sent to the server
        # or logged); the dashboard reads it on load and stores it.
        base = (config.public_url or "").rstrip("/")
        return RedirectResponse(f"{base}/hosted#token={result.token}", status_code=303)

    @router.post("/github/webhook")
    async def github_webhook(
        request: Request,
        x_github_event: str | None = Header(default=None),
        x_github_delivery: str | None = Header(default=None),
        x_hub_signature_256: str | None = Header(default=None),
    ) -> dict[str, Any]:
        raw = await request.body()
        config = load_github_app_config()
        if not verify_github_signature(raw, x_hub_signature_256, config.webhook_secret):
            raise HTTPException(status_code=401, detail={"error": "invalid GitHub signature"})
        try:
            payload = parse_webhook_payload(raw)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        installation = payload.get("installation")
        installation_id = (
            str(installation.get("id"))
            if isinstance(installation, dict) and installation.get("id") is not None
            else "anonymous"
        )
        _enforce_rate_limit(_webhook_limiter, f"webhook:{installation_id}")
        try:
            result = process_github_webhook(
                hosted,
                event=x_github_event or "unknown",
                delivery_id=x_github_delivery,
                payload=payload,
                enqueue_sync=worker.enqueue if worker is not None else None,
                config=config,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        return result.model_dump()

    return router
