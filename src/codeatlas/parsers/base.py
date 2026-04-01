"""Abstract base parser for CodeAtlas."""

from abc import ABC, abstractmethod
from pathlib import Path

from codeatlas.models import ParseResult


class BaseParser(ABC):
    """Abstract base class for all language parsers."""

    @abstractmethod
    def parse_file(self, path: Path) -> ParseResult:
        """Parse a source file from disk and return extracted symbols/relationships."""
        ...

    @abstractmethod
    def parse_source(self, source: str, file_path: str) -> ParseResult:
        """Parse source code string and return extracted symbols/relationships."""
        ...

    @property
    @abstractmethod
    def language(self) -> str:
        """The language this parser handles (e.g. 'python', 'typescript')."""
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """File extensions handled by this parser (e.g. ['.py'])."""
        ...
