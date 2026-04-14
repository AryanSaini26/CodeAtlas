"""Tree-sitter parser for Zig source files (.zig)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_zig as tszig
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

_ZIG_LANGUAGE = Language(tszig.language())

# Zig standard library namespaces to skip as call targets
_ZIG_STD = frozenset(
    {
        "std",
        "print",
        "panic",
        "assert",
        "allocPrint",
        "format",
        "parseInt",
        "parseFloat",
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


class ZigParser(BaseParser):
    """Parser for Zig source files using tree-sitter.

    Extracts:
    - @import(...) → IMPORT
    - fn declarations → FUNCTION
    - const Name = struct { ... } → CLASS
    - const Name = enum { ... } → CLASS
    - const Name = union { ... } → CLASS
    - UPPER_CASE const (non-struct/enum) → CONSTANT
    - call expressions → CALLS
    """

    def __init__(self) -> None:
        self._parser = Parser(_ZIG_LANGUAGE)

    @property
    def language(self) -> str:
        return "zig"

    @property
    def supported_extensions(self) -> list[str]:
        return [".zig"]

    def parse_file(self, path: Path) -> ParseResult:
        source = path.read_bytes()
        return self._parse(source, str(path))

    def parse_source(self, source: str, file_path: str) -> ParseResult:
        return self._parse(source.encode("utf-8"), file_path)

    def _parse(self, source: bytes, file_path: str) -> ParseResult:
        tree = self._parser.parse(source)
        symbols: list[Symbol] = []
        relationships: list[Relationship] = []
        for node in tree.root_node.named_children:
            self._visit(node, source, file_path, symbols, relationships)
        fi = FileInfo(
            path=file_path,
            language=self.language,
            content_hash=hashlib.sha256(source).hexdigest(),
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=fi, symbols=symbols, relationships=relationships)

    def _visit(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        if node.type == "function_declaration":
            self._handle_function(node, source, file_path, symbols, relationships)
        elif node.type == "variable_declaration":
            self._handle_variable(node, source, file_path, symbols)

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = next((c for c in node.children if c.type == "identifier"), None)
        if name_node is None:
            return
        name = _text(name_node, source)

        params_node = next((c for c in node.children if c.type == "parameters"), None)
        params_text = _text(params_node, source) if params_node else "()"

        # Return type: first builtin_type or identifier after parameters
        ret_node = None
        found_params = False
        for child in node.children:
            if child.type == "parameters":
                found_params = True
                continue
            if found_params and child.type in ("builtin_type", "identifier", "optional_type"):
                ret_node = child
                break
        ret_type = _text(ret_node, source) if ret_node else ""
        signature = f"fn {name}{params_text} {ret_type}".strip()

        sym = Symbol(
            id=_build_id(file_path, name),
            name=name,
            qualified_name=name,
            kind=SymbolKind.FUNCTION,
            file_path=file_path,
            span=_span(node),
            signature=signature,
            language="zig",
        )
        symbols.append(sym)

        # Collect calls inside function body
        body = next((c for c in node.children if c.type == "block"), None)
        if body:
            self._collect_calls(body, source, file_path, sym.id, relationships)

    def _handle_variable(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        name_node = next((c for c in node.children if c.type == "identifier"), None)
        if name_node is None:
            return
        name = _text(name_node, source)

        # Check RHS for @import, struct, enum, union
        rhs = None
        found_eq = False
        for child in node.children:
            if child.type == "=":
                found_eq = True
                continue
            if found_eq and child.type not in (";",):
                rhs = child
                break

        if rhs is None:
            return

        if rhs.type == "builtin_function":
            # @import("something")
            builtin_id = next((c for c in rhs.children if c.type == "builtin_identifier"), None)
            if builtin_id and _text(builtin_id, source) == "@import":
                args = next((c for c in rhs.children if c.type == "arguments"), None)
                if args:
                    str_node = next((c for c in args.named_children if c.type == "string"), None)
                    if str_node:
                        content_node = next(
                            (c for c in str_node.children if c.type == "string_content"),
                            None,
                        )
                        raw = _text(content_node, source) if content_node else name
                    else:
                        raw = name
                else:
                    raw = name
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, f"import.{raw}"),
                        name=raw,
                        qualified_name=f"import.{raw}",
                        kind=SymbolKind.IMPORT,
                        file_path=file_path,
                        span=_span(node),
                        language="zig",
                    )
                )
            return

        if rhs.type in ("struct_declaration", "enum_declaration", "union_declaration"):
            symbols.append(
                Symbol(
                    id=_build_id(file_path, name),
                    name=name,
                    qualified_name=name,
                    kind=SymbolKind.CLASS,
                    file_path=file_path,
                    span=_span(node),
                    language="zig",
                )
            )
            return

        # UPPER_CASE constant
        if name == name.upper() and name.replace("_", "").isalpha():
            symbols.append(
                Symbol(
                    id=_build_id(file_path, name),
                    name=name,
                    qualified_name=name,
                    kind=SymbolKind.CONSTANT,
                    file_path=file_path,
                    span=_span(node),
                    language="zig",
                )
            )

    def _collect_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_id: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call_expression":
            callee = next((c for c in node.children if c.type == "identifier"), None)
            if callee:
                name = _text(callee, source)
                if name not in _ZIG_STD:
                    relationships.append(
                        Relationship(
                            source_id=caller_id,
                            target_id=_build_id(file_path, name),
                            kind=RelationshipKind.CALLS,
                            file_path=file_path,
                            span=_span(node),
                        )
                    )
        for child in node.named_children:
            self._collect_calls(child, source, file_path, caller_id, relationships)
