"""HTTP/JSON API layer over GraphStore.

Sibling to ``codeatlas.server`` (the MCP surface): same store, different wire
protocol. Intended for the bundled web UI and for third-party integrations
that want a REST interface without speaking MCP.
"""

from codeatlas.api.app import create_app

__all__ = ["create_app"]
