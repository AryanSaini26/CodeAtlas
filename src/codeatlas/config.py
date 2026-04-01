"""Configuration models for CodeAtlas."""

from pathlib import Path

from pydantic import BaseModel, Field


class ParserConfig(BaseModel):
    """Configuration for the AST parser."""

    max_file_size_kb: int = Field(default=500, description="Skip files larger than this (KB)")
    include_extensions: list[str] = Field(
        default=[".py", ".ts", ".tsx", ".go"],
        description="File extensions to parse",
    )


class GraphConfig(BaseModel):
    """Configuration for the SQLite knowledge graph."""

    db_path: Path = Field(default=Path(".codeatlas/graph.db"))
    wal_mode: bool = Field(default=True, description="Enable WAL journal mode")


class ServerConfig(BaseModel):
    """Configuration for the MCP server."""

    host: str = Field(default="localhost")
    port: int = Field(default=8765)
    name: str = Field(default="codeatlas")


class CodeAtlasConfig(BaseModel):
    """Top-level configuration."""

    repo_root: Path = Field(default=Path("."))
    parser: ParserConfig = Field(default_factory=ParserConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    exclude_dirs: list[str] = Field(
        default=[
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            "dist",
            "build",
            ".mypy_cache",
        ]
    )
