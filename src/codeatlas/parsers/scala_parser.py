"""Scala AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_scala as tsscala
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

SCALA_LANGUAGE = Language(tsscala.language())


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


def _get_doc_comment(node: Node, source: bytes) -> str | None:
    """Extract preceding // or /** */ comment."""
    prev = node.prev_sibling
    while prev and prev.type in ("comment", "block_comment"):
        text = _node_text(prev, source).strip()
        if text.startswith("//"):
            return text.lstrip("/").strip()
        if text.startswith("/**") or text.startswith("/*"):
            stripped = text
            if stripped.startswith("/**"):
                stripped = stripped[3:]
            elif stripped.startswith("/*"):
                stripped = stripped[2:]
            if stripped.endswith("*/"):
                stripped = stripped[:-2]
            lines = [ln.strip().lstrip("*").strip() for ln in stripped.splitlines()]
            return "\n".join(ln for ln in lines if ln)
        break
    return None


def _get_identifier(node: Node, source: bytes) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        # First named child that's an identifier
        for child in node.named_children:
            if child.type == "identifier":
                return _node_text(child, source)
        return None
    return _node_text(name_node, source)


class ScalaParser(BaseParser):
    """Parses Scala source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(SCALA_LANGUAGE)

    @property
    def language(self) -> str:
        return "scala"

    @property
    def supported_extensions(self) -> list[str]:
        return [".scala", ".sc"]

    def parse_file(self, path: Path) -> ParseResult:
        source = path.read_bytes()
        return self._parse(source, str(path))

    def parse_source(self, source: str, file_path: str) -> ParseResult:
        return self._parse(source.encode("utf-8"), file_path)

    def _parse(self, source: bytes, file_path: str) -> ParseResult:
        content_hash = hashlib.sha256(source).hexdigest()
        tree = self._parser.parse(source)
        root = tree.root_node

        symbols: list[Symbol] = []
        relationships: list[Relationship] = []

        self._walk(root, source, file_path, symbols, relationships)

        file_info = FileInfo(
            path=file_path,
            language="scala",
            content_hash=content_hash,
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=file_info, symbols=symbols, relationships=relationships)

    def _walk(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str | None = None,
    ) -> None:
        for child in node.named_children:
            match child.type:
                case "import_declaration":
                    self._handle_import(child, source, file_path, symbols, relationships)
                case "val_definition" | "var_definition":
                    self._handle_val(child, source, file_path, symbols)
                case "trait_definition":
                    self._handle_trait(child, source, file_path, symbols, relationships)
                case "class_definition":
                    self._handle_class(child, source, file_path, symbols, relationships)
                case "object_definition":
                    self._handle_object(child, source, file_path, symbols, relationships)
                case "function_definition":
                    self._handle_function(child, source, file_path, symbols, relationships, owner)

    def _handle_import(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Reconstruct full import path from identifier chain
        parts = [_node_text(c, source) for c in node.named_children if c.type == "identifier"]
        if not parts:
            return
        module = ".".join(parts)
        short_name = parts[-1]

        symbols.append(
            Symbol(
                id=_build_id(file_path, f"import.{module}"),
                name=short_name,
                qualified_name=f"import.{module}",
                kind=SymbolKind.IMPORT,
                file_path=file_path,
                span=_node_span(node),
                language="scala",
            )
        )
        relationships.append(
            Relationship(
                source_id=_build_id(file_path, "module"),
                target_id=f"<external>::{module}",
                kind=RelationshipKind.IMPORTS,
                file_path=file_path,
                span=_node_span(node),
            )
        )

    def _handle_val(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        name = _get_identifier(node, source)
        if name is None:
            return
        # val_definition at top level are variables; no const in Scala
        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.VARIABLE,
                file_path=file_path,
                span=_node_span(node),
                language="scala",
            )
        )

    def _handle_trait(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name = _get_identifier(node, source)
        if name is None:
            return
        docstring = _get_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.INTERFACE,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="scala",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                if member.type == "function_definition":
                    self._handle_function(
                        member, source, file_path, symbols, relationships, owner=name
                    )

    def _handle_class(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name = _get_identifier(node, source)
        if name is None:
            return
        docstring = _get_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="scala",
            )
        )

        # Inheritance via extends_clause
        extends = node.child_by_field_name("extend")
        if extends:
            for type_node in extends.named_children:
                if type_node.type == "type_identifier":
                    parent = _node_text(type_node, source)
                    relationships.append(
                        Relationship(
                            source_id=_build_id(file_path, name),
                            target_id=f"<unresolved>::{parent}",
                            kind=RelationshipKind.INHERITS,
                            file_path=file_path,
                            span=_node_span(node),
                        )
                    )

        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                if member.type == "function_definition":
                    self._handle_function(
                        member, source, file_path, symbols, relationships, owner=name
                    )

    def _handle_object(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        """Handle companion objects and singleton objects."""
        name = _get_identifier(node, source)
        if name is None:
            return
        docstring = _get_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="scala",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                if member.type == "function_definition":
                    self._handle_function(
                        member, source, file_path, symbols, relationships, owner=name
                    )

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str | None = None,
    ) -> None:
        name = _get_identifier(node, source)
        if name is None:
            return
        qualified_name = f"{owner}.{name}" if owner else name
        kind = SymbolKind.METHOD if owner else SymbolKind.FUNCTION
        docstring = _get_doc_comment(node, source)

        params = node.child_by_field_name("parameters")
        return_type = node.child_by_field_name("return_type")
        sig = f"def {name}"
        if params:
            sig += _node_text(params, source)
        if return_type:
            sig += f": {_node_text(return_type, source)}"

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=kind,
                file_path=file_path,
                span=_node_span(node),
                signature=sig,
                docstring=docstring,
                language="scala",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_qualified: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call_expression":
            fn_node = node.child_by_field_name("function")
            if fn_node:
                callee = _node_text(fn_node, source)
                relationships.append(
                    Relationship(
                        source_id=_build_id(file_path, caller_qualified),
                        target_id=f"<unresolved>::{callee}",
                        kind=RelationshipKind.CALLS,
                        file_path=file_path,
                        span=_node_span(node),
                    )
                )
        for child in node.children:
            self._extract_calls(child, source, file_path, caller_qualified, relationships)
