"""Tree-sitter parser for Swift source files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter_swift as tsswift
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

if TYPE_CHECKING:
    pass

_SWIFT_LANGUAGE = Language(tsswift.language())


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


def _get_doc_comment(node: Node, source: bytes) -> str | None:
    """Collect preceding /// or /** */ comment lines."""
    lines: list[str] = []
    prev = node.prev_sibling
    while prev is not None and prev.type in ("comment", "multiline_comment"):
        text = _node_text(prev, source).strip()
        if text.startswith("///"):
            lines.append(text.lstrip("/").strip())
        elif text.startswith("/**"):
            inner = text[3:]
            if inner.endswith("*/"):
                inner = inner[:-2]
            lines.append(inner.strip())
        prev = prev.prev_sibling
    return "\n".join(reversed(lines)) if lines else None


class SwiftParser(BaseParser):
    """Parser for Swift source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(_SWIFT_LANGUAGE)

    @property
    def language(self) -> str:
        return "swift"

    @property
    def supported_extensions(self) -> list[str]:
        return [".swift"]

    def parse_file(self, path: Path) -> ParseResult:
        source = path.read_bytes()
        return self._parse(source, str(path))

    def parse_source(self, source: str, file_path: str) -> ParseResult:
        return self._parse(source.encode("utf-8"), file_path)

    def _parse(self, source: bytes, file_path: str) -> ParseResult:
        tree = self._parser.parse(source)
        symbols: list[Symbol] = []
        relationships: list[Relationship] = []

        self._visit(tree.root_node, source, file_path, None, symbols, relationships)

        fi = FileInfo(
            path=file_path,
            language=self.language,
            content_hash=hashlib.sha256(source).hexdigest(),
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=fi, symbols=symbols, relationships=relationships)

    # ------------------------------------------------------------------ #
    # Visitor                                                              #
    # ------------------------------------------------------------------ #

    def _visit(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str | None,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        match node.type:
            case "import_declaration":
                self._handle_import(node, source, file_path, symbols, relationships)
            case "class_declaration":
                self._handle_type_decl(node, source, file_path, parent_name, symbols, relationships)
            case "protocol_declaration":
                self._handle_protocol(node, source, file_path, parent_name, symbols, relationships)
            case "function_declaration":
                self._handle_function(node, source, file_path, parent_name, symbols, relationships)
            case "typealias_declaration":
                self._handle_typealias(node, source, file_path, parent_name, symbols)
            case _:
                for child in node.named_children:
                    self._visit(child, source, file_path, parent_name, symbols, relationships)

    # ------------------------------------------------------------------ #
    # Declarations                                                         #
    # ------------------------------------------------------------------ #

    def _handle_import(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # import_declaration: 'import' module_name
        parts = [c for c in node.named_children if c.type not in ("import",)]
        if not parts:
            return
        name = _node_text(parts[-1], source).strip()
        sym = Symbol(
            id=_build_id(file_path, f"import.{name}"),
            name=name,
            qualified_name=f"import.{name}",
            kind=SymbolKind.IMPORT,
            file_path=file_path,
            span=_node_span(node),
            language="swift",
        )
        symbols.append(sym)
        relationships.append(
            Relationship(
                source_id=_build_id(file_path, "module"),
                target_id=f"<external>::{name}",
                kind=RelationshipKind.IMPORTS,
                file_path=file_path,
                span=_node_span(node),
            )
        )

    def _handle_type_decl(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str | None,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        """Handle class, struct, enum, actor declarations (all are class_declaration in tree-sitter-swift)."""
        name_node = node.child_by_field_name("name") or next(
            (c for c in node.named_children if c.type == "type_identifier"), None
        )
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = f"{parent_name}.{name}" if parent_name else name

        # Determine actual kind from preceding keyword sibling
        kind = SymbolKind.CLASS
        raw = _node_text(node, source)
        if raw.lstrip().startswith("struct "):
            kind = SymbolKind.CLASS  # treat struct as class
        elif raw.lstrip().startswith("enum "):
            kind = SymbolKind.ENUM if hasattr(SymbolKind, "ENUM") else SymbolKind.CLASS

        sym = Symbol(
            id=_build_id(file_path, qualified),
            name=name,
            qualified_name=qualified,
            kind=kind,
            file_path=file_path,
            span=_node_span(node),
            docstring=_get_doc_comment(node, source),
            language="swift",
        )
        symbols.append(sym)

        # Inheritance
        for child in node.named_children:
            if child.type == "inheritance_specifier":
                # inheritance_specifier → user_type → type_identifier
                type_id = next(
                    (c for c in child.named_children if c.type in ("user_type", "type_identifier")),
                    None,
                )
                if type_id is not None:
                    parent_type = _node_text(type_id, source).strip()
                    relationships.append(
                        Relationship(
                            source_id=sym.id,
                            target_id=f"<unresolved>::{parent_type}",
                            kind=RelationshipKind.INHERITS,
                            file_path=file_path,
                            span=_node_span(child),
                        )
                    )

        # Recurse into body
        body = next((c for c in node.named_children if c.type == "class_body"), None)
        if body:
            for child in body.named_children:
                self._visit(child, source, file_path, qualified, symbols, relationships)

    def _handle_protocol(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str | None,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = next((c for c in node.named_children if c.type == "type_identifier"), None)
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = f"{parent_name}.{name}" if parent_name else name

        sym = Symbol(
            id=_build_id(file_path, qualified),
            name=name,
            qualified_name=qualified,
            kind=SymbolKind.INTERFACE,
            file_path=file_path,
            span=_node_span(node),
            docstring=_get_doc_comment(node, source),
            language="swift",
        )
        symbols.append(sym)

        # Protocol body members
        body = next((c for c in node.named_children if c.type == "protocol_body"), None)
        if body:
            for child in body.named_children:
                self._visit(child, source, file_path, qualified, symbols, relationships)

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str | None,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = next((c for c in node.named_children if c.type == "simple_identifier"), None)
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = f"{parent_name}.{name}" if parent_name else name
        kind = SymbolKind.METHOD if parent_name else SymbolKind.FUNCTION

        # Build signature from parameter children
        params = [c for c in node.named_children if c.type == "parameter"]
        if params:
            params_text = "(" + ", ".join(_node_text(p, source) for p in params) + ")"
        else:
            params_text = "()"
        signature = f"func {name}{params_text}"

        # Check for return type (user_type or optional_type sibling after params)
        named = node.named_children
        ret_candidates = [
            c
            for c in named
            if c.type in ("user_type", "optional_type", "function_type", "tuple_type")
            and c not in params
            and c.start_byte > (params[-1].end_byte if params else 0)
        ]
        if ret_candidates:
            signature += f" -> {_node_text(ret_candidates[0], source).strip()}"

        # Decorators / modifiers
        decorators: list[str] = []
        modifiers = next((c for c in node.named_children if c.type == "modifiers"), None)
        if modifiers:
            for mod in modifiers.named_children:
                decorators.append(_node_text(mod, source).strip())

        sym = Symbol(
            id=_build_id(file_path, qualified),
            name=name,
            qualified_name=qualified,
            kind=kind,
            file_path=file_path,
            span=_node_span(node),
            docstring=_get_doc_comment(node, source),
            signature=signature,
            decorators=decorators,
            language="swift",
        )
        symbols.append(sym)

        # Calls inside function body
        body = next((c for c in node.named_children if c.type == "function_body"), None)
        if body:
            self._collect_calls(body, source, file_path, sym.id, relationships)

    def _handle_typealias(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str | None,
        symbols: list[Symbol],
    ) -> None:
        name_node = next((c for c in node.named_children if c.type == "type_identifier"), None)
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = f"{parent_name}.{name}" if parent_name else name
        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.TYPE_ALIAS,
                file_path=file_path,
                span=_node_span(node),
                language="swift",
            )
        )

    # ------------------------------------------------------------------ #
    # Call extraction                                                      #
    # ------------------------------------------------------------------ #

    def _collect_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_id: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call_expression":
            callee = node.named_children[0] if node.named_children else None
            if callee is not None:
                name: str | None = None
                if callee.type == "simple_identifier":
                    name = _node_text(callee, source)
                elif callee.type == "navigation_expression":
                    # obj.method → take the last identifier
                    suffix = next(
                        (c for c in callee.named_children if c.type == "navigation_suffix"), None
                    )
                    if suffix:
                        ident = next(
                            (c for c in suffix.named_children if c.type == "simple_identifier"),
                            None,
                        )
                        name = _node_text(ident, source) if ident else None
                    else:
                        name = None
                else:
                    name = None
                if name:
                    relationships.append(
                        Relationship(
                            source_id=caller_id,
                            target_id=f"<unresolved>::{name}",
                            kind=RelationshipKind.CALLS,
                            file_path=file_path,
                            span=_node_span(node),
                        )
                    )
        for child in node.named_children:
            self._collect_calls(child, source, file_path, caller_id, relationships)
