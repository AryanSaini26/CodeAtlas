"""Tree-sitter parser for SQL source files (.sql)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_sql as tssql
from tree_sitter import Language, Node, Parser

from codeatlas.models import (
    FileInfo,
    ParseResult,
    Position,
    Relationship,
    RelationshipKind,
    Span,
    Symbol,
    SymbolKind,
)
from codeatlas.parsers.base import BaseParser

_SQL_LANGUAGE = Language(tssql.language())

# SQL built-ins / system tables to skip as CALLS targets
_SQL_BUILTINS = frozenset(
    {
        "dual",
        "information_schema",
        "pg_catalog",
        "sys",
        "mysql",
        "sqlite_master",
        "sqlite_temp_master",
    }
)


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _build_id(file_path: str, name: str) -> str:
    return f"{file_path}::{name}"


def _get_object_name(node: Node, source: bytes) -> str | None:
    """Extract the last identifier from an object_reference (handles schema.table)."""
    ref = next(
        (c for c in node.named_children if c.type == "object_reference"),
        None,
    )
    if ref is None:
        return None
    idents = [c for c in ref.named_children if c.type == "identifier"]
    if not idents:
        return None
    return _text(idents[-1], source)


def _collect_table_refs(node: Node, source: bytes) -> list[str]:
    """Recursively collect all table/view references from FROM and JOIN clauses."""
    refs: list[str] = []
    if node.type in ("from", "join"):
        for child in node.named_children:
            if child.type == "relation":
                ref = next((c for c in child.named_children if c.type == "object_reference"), None)
                if ref:
                    idents = [c for c in ref.named_children if c.type == "identifier"]
                    if idents:
                        name = _text(idents[-1], source)
                        if name.lower() not in _SQL_BUILTINS:
                            refs.append(name)
    for child in node.named_children:
        refs.extend(_collect_table_refs(child, source))
    return refs


class SqlParser(BaseParser):
    """Parser for SQL files using tree-sitter.

    Extracts:
    - CREATE TABLE / CREATE VIEW → CLASS
    - CREATE FUNCTION / CREATE PROCEDURE → FUNCTION
    - Table/view references inside function and view bodies → CALLS
    """

    def __init__(self) -> None:
        self._parser = Parser(_SQL_LANGUAGE)

    @property
    def language(self) -> str:
        return "sql"

    @property
    def supported_extensions(self) -> list[str]:
        return [".sql"]

    def parse_file(self, path: Path) -> ParseResult:
        source = path.read_bytes()
        return self._parse(source, str(path))

    def parse_source(self, source: str, file_path: str) -> ParseResult:
        return self._parse(source.encode("utf-8"), file_path)

    def _parse(self, source: bytes, file_path: str) -> ParseResult:
        tree = self._parser.parse(source)
        symbols: list[Symbol] = []
        relationships: list[Relationship] = []

        for stmt_wrapper in tree.root_node.named_children:
            # Each top-level child is a `statement` node
            for stmt in stmt_wrapper.named_children:
                self._handle_statement(stmt, source, file_path, symbols, relationships)

        fi = FileInfo(
            path=file_path,
            language=self.language,
            content_hash=hashlib.sha256(source).hexdigest(),
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=fi, symbols=symbols, relationships=relationships)

    def _handle_statement(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        if node.type == "create_table":
            self._handle_table(node, source, file_path, symbols)
        elif node.type == "create_view":
            self._handle_view(node, source, file_path, symbols, relationships)
        elif node.type in ("create_function", "create_procedure"):
            self._handle_function(node, source, file_path, symbols, relationships)

    def _handle_table(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        name = _get_object_name(node, source)
        if not name:
            return
        # Collect column names for a lightweight signature
        col_defs = next((c for c in node.named_children if c.type == "column_definitions"), None)
        cols: list[str] = []
        if col_defs:
            for col in col_defs.named_children:
                if col.type == "column_definition":
                    col_ident = next(
                        (c for c in col.named_children if c.type == "identifier"), None
                    )
                    if col_ident:
                        cols.append(_text(col_ident, source))
        signature = f"TABLE {name}({', '.join(cols)})" if cols else f"TABLE {name}"
        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_span(node),
                signature=signature,
                language="sql",
            )
        )

    def _handle_view(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name = _get_object_name(node, source)
        if not name:
            return
        sym = Symbol(
            id=_build_id(file_path, name),
            name=name,
            qualified_name=name,
            kind=SymbolKind.CLASS,
            file_path=file_path,
            span=_span(node),
            signature=f"VIEW {name}",
            language="sql",
        )
        symbols.append(sym)
        # Table references inside the view body
        for ref_name in _collect_table_refs(node, source):
            if ref_name != name:
                relationships.append(
                    Relationship(
                        source_id=sym.id,
                        target_id=_build_id(file_path, ref_name),
                        kind=RelationshipKind.CALLS,
                        file_path=file_path,
                        span=_span(node),
                    )
                )

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name = _get_object_name(node, source)
        if not name:
            return
        # Build parameter signature
        args_node = next((c for c in node.named_children if c.type == "function_arguments"), None)
        args_text = _text(args_node, source).strip() if args_node else "()"
        if not args_text.startswith("("):
            args_text = f"({args_text})"
        keyword = "PROCEDURE" if node.type == "create_procedure" else "FUNCTION"
        sig = f"{keyword} {name}{args_text}"

        sym = Symbol(
            id=_build_id(file_path, name),
            name=name,
            qualified_name=name,
            kind=SymbolKind.FUNCTION,
            file_path=file_path,
            span=_span(node),
            signature=sig,
            language="sql",
        )
        symbols.append(sym)
        # Table references inside function body
        body = next((c for c in node.named_children if c.type == "function_body"), None)
        if body:
            for ref_name in _collect_table_refs(body, source):
                if ref_name != name:
                    relationships.append(
                        Relationship(
                            source_id=sym.id,
                            target_id=_build_id(file_path, ref_name),
                            kind=RelationshipKind.CALLS,
                            file_path=file_path,
                            span=_span(node),
                        )
                    )
