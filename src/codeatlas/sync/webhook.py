"""GitHub webhook handler for real-time graph updates on push events."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import subprocess
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from codeatlas.graph.store import GraphStore
from codeatlas.parsers import ParserRegistry

logger = logging.getLogger(__name__)


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify the GitHub webhook HMAC-SHA256 signature."""
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _extract_changed_files(payload: dict) -> tuple[list[str], list[str]]:
    """Extract added/modified and removed file paths from a push event.

    Returns (changed_files, removed_files).
    """
    changed: set[str] = set()
    removed: set[str] = set()

    for commit in payload.get("commits", []):
        changed.update(commit.get("added", []))
        changed.update(commit.get("modified", []))
        removed.update(commit.get("removed", []))

    # A file that was removed shouldn't also be in changed
    changed -= removed
    return sorted(changed), sorted(removed)


def _pull_latest(repo_root: Path) -> bool:
    """Run git pull to get the latest changes."""
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error("git pull failed: %s", result.stderr)
            return False
        return True
    except Exception as exc:
        logger.error("git pull error: %s", exc)
        return False


class WebhookHandler:
    """Handles GitHub push webhooks and triggers incremental graph updates."""

    def __init__(
        self,
        store: GraphStore,
        repo_root: Path,
        secret: str | None = None,
        auto_pull: bool = True,
    ) -> None:
        self._store = store
        self._repo_root = repo_root
        self._registry = ParserRegistry()
        self._secret = secret
        self._auto_pull = auto_pull

    async def handle_push(self, request: Request) -> Response:
        """Process a GitHub push webhook event."""
        body = await request.body()

        # Verify signature if secret is configured
        if self._secret:
            sig = request.headers.get("X-Hub-Signature-256", "")
            if not _verify_signature(body, sig, self._secret):
                return JSONResponse({"error": "invalid signature"}, status_code=403)

        # Only handle push events
        event = request.headers.get("X-GitHub-Event", "")
        if event == "ping":
            return JSONResponse({"status": "pong"})
        if event != "push":
            return JSONResponse({"status": "ignored", "event": event})

        payload = json.loads(body)
        changed_files, removed_files = _extract_changed_files(payload)

        if not changed_files and not removed_files:
            return JSONResponse({"status": "no_changes"})

        # Pull latest code
        if self._auto_pull:
            if not _pull_latest(self._repo_root):
                return JSONResponse({"error": "git pull failed"}, status_code=500)

        # Process removals
        for path in removed_files:
            self._store.delete_file(str(self._repo_root / path))
            logger.info("Removed from graph: %s", path)

        # Process additions and modifications
        parsed = 0
        errors = 0
        for path in changed_files:
            full_path = self._repo_root / path
            if not full_path.exists():
                continue
            try:
                result = self._registry.parse_file(full_path)
                if result is not None:
                    self._store.upsert_parse_result(result)
                    parsed += 1
            except Exception as exc:
                logger.error("Error parsing %s: %s", path, exc)
                errors += 1

        # Re-resolve imports after updates
        if parsed > 0:
            self._store.resolve_imports()

        return JSONResponse({
            "status": "ok",
            "parsed": parsed,
            "removed": len(removed_files),
            "errors": errors,
        })

    async def health(self, request: Request) -> Response:
        """Health check endpoint."""
        stats = self._store.get_stats()
        return JSONResponse({"status": "healthy", "graph": stats})

    def create_app(self) -> Starlette:
        """Create the Starlette ASGI app with webhook routes."""
        return Starlette(
            routes=[
                Route("/webhook", self.handle_push, methods=["POST"]),
                Route("/health", self.health, methods=["GET"]),
            ],
        )
