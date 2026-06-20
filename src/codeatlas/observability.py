"""Optional observability hooks.

CodeAtlas should run without OpenTelemetry installed. When the dependency is
present in an embedding application, these helpers create spans; otherwise they
are deterministic no-ops.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[None]:
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
    except ImportError:
        yield
        return

    tracer = trace.get_tracer("codeatlas")
    with tracer.start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            span.set_attribute(key, value)
        yield


# --- Prometheus metrics (optional; the `api` extra installs prometheus-client) ---

_metrics: dict[str, Any] | None = None


def _get_metrics() -> dict[str, Any] | None:
    """Lazily create the metric collectors once; no-op if the dep is absent."""
    global _metrics
    if _metrics is None:
        try:
            from prometheus_client import Counter, Histogram

            _metrics = {
                "requests": Counter(
                    "codeatlas_http_requests_total",
                    "HTTP requests by route prefix, method, and status.",
                    ["prefix", "method", "status"],
                ),
                "latency": Histogram(
                    "codeatlas_http_request_duration_seconds",
                    "HTTP request latency by route prefix.",
                    ["prefix"],
                ),
                "sync": Counter(
                    "codeatlas_sync_jobs_total",
                    "Hosted sync jobs by terminal status.",
                    ["status"],
                ),
            }
        except Exception:
            _metrics = {}
    return _metrics or None


def record_request(prefix: str, method: str, status: int, duration_seconds: float) -> None:
    metrics = _get_metrics()
    if not metrics:
        return
    metrics["requests"].labels(prefix=prefix, method=method, status=str(status)).inc()
    metrics["latency"].labels(prefix=prefix).observe(duration_seconds)


def record_sync(status: str) -> None:
    metrics = _get_metrics()
    if not metrics:
        return
    metrics["sync"].labels(status=status).inc()


def metrics_exposition() -> tuple[bytes, str] | None:
    """Return (body, content_type) for /metrics, or None if the dep is absent."""
    if _get_metrics() is None:
        return None
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return generate_latest(), CONTENT_TYPE_LATEST
