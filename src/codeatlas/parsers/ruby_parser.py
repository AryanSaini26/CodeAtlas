"""Ruby AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_ruby as tsruby
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

RUBY_LANGUAGE = Language(tsruby.language())


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
    """Extract preceding # comment lines as docstring."""
    lines: list[str] = []
    prev = node.prev_sibling
    while prev and prev.type == "comment":
        text = _node_text(prev, source)
        lines.insert(0, text.lstrip("#").strip())
        prev = prev.prev_sibling
    return "\n".join(lines) if lines else None


class RubyParser(BaseParser):
    """Parses Ruby source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(RUBY_LANGUAGE)

    @property
    def language(self) -> str:
        return "ruby"

    @property
    def supported_extensions(self) -> list[str]:
        return [".rb"]

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

        self._walk_toplevel(root, source, file_path, symbols, relationships)

        file_info = FileInfo(
            path=file_path,
            language="ruby",
            content_hash=content_hash,
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=file_info, symbols=symbols, relationships=relationships)

    def _walk_toplevel(
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
                case "call":
                    self._handle_call_toplevel(child, source, file_path, symbols, relationships)
                case "assignment":
                    self._handle_constant(child, source, file_path, symbols)
                case "module":
                    self._handle_module(child, source, file_path, symbols, relationships)
                case "class":
                    self._handle_class(child, source, file_path, symbols, relationships)
                case "method":
                    self._handle_method(child, source, file_path, symbols, relationships, owner)
                case "singleton_method":
                    self._handle_singleton_method(
                        child, source, file_path, symbols, relationships, owner
                    )

    def _handle_call_toplevel(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        """Handle top-level require/require_relative calls."""
        method_node = node.child_by_field_name("method")
        if method_node is None:
            return
        method_name = _node_text(method_node, source)
        if method_name not in ("require", "require_relative"):
            return

        args = node.child_by_field_name("arguments")
        if args is None:
            return
        # First string argument is the path/gem name
        for arg in args.named_children:
            if arg.type == "string":
                # Strip string delimiters
                raw = _node_text(arg, source).strip("'\"")
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, f"require.{raw}"),
                        name=raw,
                        qualified_name=f"require.{raw}",
                        kind=SymbolKind.IMPORT,
                        file_path=file_path,
                        span=_node_span(node),
                        language="ruby",
                    )
                )
                relationships.append(
                    Relationship(
                        source_id=_build_id(file_path, "module"),
                        target_id=f"<external>::{raw}",
                        kind=RelationshipKind.IMPORTS,
                        file_path=file_path,
                        span=_node_span(node),
                    )
                )
                break

    def _handle_constant(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        """Handle CONST = value assignments."""
        lhs = node.child_by_field_name("left")
        if lhs is None or lhs.type != "constant":
            return
        name = _node_text(lhs, source)
        docstring = _get_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CONSTANT,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="ruby",
            )
        )

    def _handle_module(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        docstring = _get_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.MODULE,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="ruby",
            )
        )

        # Walk module body
        body = node.child_by_field_name("body")
        if body:
            self._walk_toplevel(body, source, file_path, symbols, relationships, owner=name)

    def _handle_class(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
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
                language="ruby",
            )
        )

        # Inheritance relationship
        superclass_node = node.child_by_field_name("superclass")
        if superclass_node:
            superclass = _node_text(superclass_node, source)
            relationships.append(
                Relationship(
                    source_id=_build_id(file_path, name),
                    target_id=f"<unresolved>::{superclass}",
                    kind=RelationshipKind.INHERITS,
                    file_path=file_path,
                    span=_node_span(node),
                )
            )

        # Walk class body
        body = node.child_by_field_name("body")
        if body:
            self._walk_toplevel(body, source, file_path, symbols, relationships, owner=name)

    def _handle_method(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str | None = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{owner}.{name}" if owner else name
        kind = SymbolKind.METHOD if owner else SymbolKind.FUNCTION
        docstring = _get_doc_comment(node, source)
        signature = self._build_signature(node, source, name)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=kind,
                file_path=file_path,
                span=_node_span(node),
                signature=signature,
                docstring=docstring,
                language="ruby",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _handle_singleton_method(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str | None = None,
    ) -> None:
        """Handle def self.method_name definitions."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{owner}.self.{name}" if owner else f"self.{name}"
        docstring = _get_doc_comment(node, source)
        signature = self._build_signature(node, source, f"self.{name}")

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=SymbolKind.METHOD,
                file_path=file_path,
                span=_node_span(node),
                signature=signature,
                docstring=docstring,
                language="ruby",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _build_signature(self, node: Node, source: bytes, name: str) -> str:
        params = node.child_by_field_name("parameters")
        if params:
            return f"def {name}{_node_text(params, source)}"
        return f"def {name}"

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_qualified: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call":
            method_node = node.child_by_field_name("method")
            receiver_node = node.child_by_field_name("receiver")
            if method_node:
                method = _node_text(method_node, source)
                receiver = _node_text(receiver_node, source) if receiver_node else None
                callee = f"{receiver}.{method}" if receiver else method
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
