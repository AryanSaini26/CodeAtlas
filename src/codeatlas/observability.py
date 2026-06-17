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
