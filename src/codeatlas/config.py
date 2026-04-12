"""Configuration models for CodeAtlas."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class ParserConfig(BaseModel):
    """Configuration for the AST parser."""

    max_file_size_kb: int = Field(default=500, description="Skip files larger than this (KB)")
    include_extensions: list[str] = Field(
        default=[
            ".py",
            ".ts",
            ".tsx",
            ".go",
            ".rs",
            ".java",
            ".cpp",
            ".cc",
            ".cxx",
            ".hpp",
            ".hxx",
            ".h",
            ".cs",
            ".rb",
            ".js",
            ".mjs",
            ".cjs",
            ".kt",
            ".kts",
            ".php",
            ".scala",
            ".sc",
            ".sh",
            ".bash",
            ".lua",
            ".ex",
            ".exs",
        ],
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

    @classmethod
    def from_toml(cls, path: Path) -> "CodeAtlasConfig":
        """Load configuration from a TOML file."""
        data = tomllib.loads(path.read_text())
        config_data = data.get("codeatlas", data)
        return cls(**config_data)

    @classmethod
    def find_and_load(cls, repo_root: Path) -> "CodeAtlasConfig":
        """Look for codeatlas.toml in the repo root and load it, or return defaults."""
        toml_path = repo_root / "codeatlas.toml"
        if toml_path.exists():
            config = cls.from_toml(toml_path)
            if config.repo_root == Path("."):
                config.repo_root = repo_root
            return config
        return cls(repo_root=repo_root)
