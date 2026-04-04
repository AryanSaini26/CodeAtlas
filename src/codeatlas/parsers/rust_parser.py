"""Rust AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_rust as tsrust
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

RUST_LANGUAGE = Language(tsrust.language())


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
    """Extract preceding /// doc comments."""
    lines: list[str] = []
    prev = node.prev_sibling
    while prev and prev.type == "line_comment":
        text = _node_text(prev, source)
        if text.startswith("///"):
            lines.insert(0, text[3:].strip())
            prev = prev.prev_sibling
        else:
            break
    return "\n".join(lines) if lines else None


def _is_pub(node: Node) -> bool:
    """Check if the node has a pub visibility modifier."""
    for child in node.children:
        if child.type == "visibility_modifier":
            return True
    return False


def _is_async(node: Node) -> bool:
    """Check if a function has the async modifier."""
    for child in node.children:
        if child.type == "function_modifiers":
            for mod in child.children:
                if mod.type == "async":
                    return True
    return False


class RustParser(BaseParser):
    """Parses Rust source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(RUST_LANGUAGE)

    @property
    def language(self) -> str:
        return "rust"

    @property
    def supported_extensions(self) -> list[str]:
        return [".rs"]

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

        for child in root.children:
            match child.type:
                case "use_declaration":
                    self._handle_use(child, source, file_path, symbols, relationships)
                case "function_item":
                    self._handle_function(child, source, file_path, symbols, relationships)
                case "struct_item":
                    self._handle_struct(child, source, file_path, symbols, relationships)
                case "enum_item":
                    self._handle_enum(child, source, file_path, symbols)
                case "trait_item":
                    self._handle_trait(child, source, file_path, symbols)
                case "impl_item":
                    self._handle_impl(child, source, file_path, symbols, relationships)
                case "type_item":
                    self._handle_type_alias(child, source, file_path, symbols)
                case "const_item":
                    self._handle_const(child, source, file_path, symbols)
                case "static_item":
                    self._handle_static(child, source, file_path, symbols)
                case "mod_item":
                    self._handle_mod(child, source, file_path, symbols)

        file_info = FileInfo(
            path=file_path,
            language="rust",
            content_hash=content_hash,
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=file_info, symbols=symbols, relationships=relationships)

    def _handle_use(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Extract the full use path text (between 'use' and ';')
        use_text = _node_text(node, source)
        # Strip 'use ' prefix and ';' suffix
        path_text = use_text.removeprefix("use ").removesuffix(";").strip()

        symbols.append(
            Symbol(
                id=_build_id(file_path, f"use.{path_text}"),
                name=path_text.rsplit("::", 1)[-1],
                qualified_name=f"use.{path_text}",
                kind=SymbolKind.IMPORT,
                file_path=file_path,
                span=_node_span(node),
                language="rust",
            )
        )
        relationships.append(
            Relationship(
                source_id=_build_id(file_path, "module"),
                target_id=f"<external>::{path_text}",
                kind=RelationshipKind.IMPORTS,
                file_path=file_path,
                span=_node_span(node),
            )
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
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{owner}.{name}" if owner else name

        signature = self._build_signature(node, source, name)
        docstring = _get_doc_comment(node, source)

        kind = SymbolKind.METHOD if owner else SymbolKind.FUNCTION

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
                language="rust",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _handle_struct(
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
                language="rust",
            )
        )

    def _handle_enum(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
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
                kind=SymbolKind.ENUM,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="rust",
            )
        )

    def _handle_trait(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
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
                kind=SymbolKind.INTERFACE,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="rust",
            )
        )

    def _handle_impl(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Determine the type being impl'd
        type_node = node.child_by_field_name("type")
        if type_node is None:
            return
        impl_type = _node_text(type_node, source)

        # Check if this is a trait impl: impl Trait for Type
        trait_node = node.child_by_field_name("trait")
        if trait_node:
            trait_name = _node_text(trait_node, source)
            relationships.append(
                Relationship(
                    source_id=_build_id(file_path, impl_type),
                    target_id=f"<unresolved>::{trait_name}",
                    kind=RelationshipKind.IMPLEMENTS,
                    file_path=file_path,
                    span=_node_span(node),
                )
            )

        # Extract methods from the impl block
        body = node.child_by_field_name("body")
        if body is None:
            return
        for child in body.named_children:
            if child.type == "function_item":
                self._handle_function(
                    child, source, file_path, symbols, relationships, owner=impl_type
                )

    def _handle_type_alias(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.TYPE_ALIAS,
                file_path=file_path,
                span=_node_span(node),
                language="rust",
            )
        )

    def _handle_const(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CONSTANT,
                file_path=file_path,
                span=_node_span(node),
                language="rust",
            )
        )

    def _handle_static(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.VARIABLE,
                file_path=file_path,
                span=_node_span(node),
                language="rust",
            )
        )

    def _handle_mod(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.MODULE,
                file_path=file_path,
                span=_node_span(node),
                language="rust",
            )
        )

    def _build_signature(self, node: Node, source: bytes, name: str) -> str:
        async_prefix = "async " if _is_async(node) else ""
        params = node.child_by_field_name("parameters")
        return_type = node.child_by_field_name("return_type")
        sig = f"{async_prefix}fn {name}"
        if params:
            sig += _node_text(params, source)
        if return_type:
            sig += f" -> {_node_text(return_type, source)}"
        return sig

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_qualified: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            if func_node:
                callee = _node_text(func_node, source)
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
