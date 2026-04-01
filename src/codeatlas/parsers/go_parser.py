"""Go AST parser using tree-sitter (stub - to be implemented in Month 1)."""

import hashlib
from pathlib import Path

from codeatlas.models import FileInfo, ParseResult
from codeatlas.parsers.base import BaseParser


class GoParser(BaseParser):
    """Parses Go source files using tree-sitter. Currently a stub."""

    @property
    def language(self) -> str:
        return "go"

    @property
    def supported_extensions(self) -> list[str]:
        return [".go"]

    def parse_file(self, path: Path) -> ParseResult:
        source = path.read_bytes()
        return self._stub_result(source, str(path))

    def parse_source(self, source: str, file_path: str) -> ParseResult:
        return self._stub_result(source.encode("utf-8"), file_path)

    def _stub_result(self, source: bytes, file_path: str) -> ParseResult:
        return ParseResult(
            file_info=FileInfo(
                path=file_path,
                language="go",
                content_hash=hashlib.sha256(source).hexdigest(),
                size_bytes=len(source),
            )
        )
