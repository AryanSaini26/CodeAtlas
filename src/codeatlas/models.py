"""Core data models for CodeAtlas."""

from enum import StrEnum

from pydantic import BaseModel, Field


class SymbolKind(StrEnum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    CONSTANT = "constant"
    VARIABLE = "variable"
    IMPORT = "import"
    MODULE = "module"
    TYPE_ALIAS = "type_alias"
    ENUM = "enum"
    NAMESPACE = "namespace"


class RelationshipKind(StrEnum):
    CALLS = "calls"
    IMPORTS = "imports"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    DECORATES = "decorates"
    DEFINES = "defines"
    REFERENCES = "references"


class Confidence(StrEnum):
    """How trustworthy a relationship's target resolution is.

    - ``EXTRACTED`` — the target was directly present in the parser output
      (same-file resolution or verbatim ID match). Highest confidence.
    - ``INFERRED`` — the target was resolved by name-lookup with a single
      unambiguous match. Likely correct but not AST-proven.
    - ``AMBIGUOUS`` — multiple candidate targets existed; a heuristic
      chose one. Treat with caution.
    """

    EXTRACTED = "extracted"
    INFERRED = "inferred"
    AMBIGUOUS = "ambiguous"


class Position(BaseModel):
    line: int
    column: int


class Span(BaseModel):
    start: Position
    end: Position


class Symbol(BaseModel):
    """A named code entity extracted from a source file."""

    id: str = Field(description="Unique identifier: file_path::qualified.name")
    name: str
    qualified_name: str = Field(description="Dot-separated fully qualified name within the file")
    kind: SymbolKind
    file_path: str
    span: Span
    docstring: str | None = None
    signature: str | None = None
    decorators: list[str] = Field(default_factory=list)
    language: str = "unknown"
    is_test: bool = Field(default=False, description="True if symbol lives in a test file")


class Relationship(BaseModel):
    """A directed edge between two symbols."""

    source_id: str
    target_id: str
    kind: RelationshipKind
    file_path: str
    span: Span | None = None
    confidence: Confidence = Confidence.EXTRACTED


class FileInfo(BaseModel):
    """Metadata about a parsed source file."""

    path: str
    language: str
    content_hash: str
    symbol_count: int = 0
    relationship_count: int = 0
    size_bytes: int = 0


class ParseResult(BaseModel):
    """Everything extracted from a single source file."""

    file_info: FileInfo
    symbols: list[Symbol] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
