"""Lua AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_lua as tslua
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

LUA_LANGUAGE = Language(tslua.language())


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
    """Extract preceding -- comment."""
    prev = node.prev_sibling
    while prev and prev.type == "comment":
        # Strip -- prefix from comment_content child or raw text
        text = _node_text(prev, source)
        for child in prev.named_children:
            return _node_text(child, source).strip()
        return text.lstrip("-").strip()
    return None


class LuaParser(BaseParser):
    """Parses Lua source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(LUA_LANGUAGE)

    @property
    def language(self) -> str:
        return "lua"

    @property
    def supported_extensions(self) -> list[str]:
        return [".lua"]

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
            language="lua",
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
    ) -> None:
        for child in node.named_children:
            match child.type:
                case "function_declaration":
                    self._handle_function(child, source, file_path, symbols, relationships)
                case "local_function":
                    self._handle_function(child, source, file_path, symbols, relationships)
                case "variable_declaration":
                    self._handle_variable(child, source, file_path, symbols, relationships)

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Name can be 'identifier' or 'dot_index_expression' (M.greet)
        name_node = node.named_children[0] if node.named_children else None
        if name_node is None:
            return
        name = _node_text(name_node, source)
        docstring = _get_doc_comment(node, source)

        params = None
        for child in node.named_children:
            if child.type == "parameters":
                params = child
                break

        sig = f"function {name}"
        if params:
            sig += _node_text(params, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name.rsplit(".", 1)[-1],
                qualified_name=name,
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                span=_node_span(node),
                signature=sig,
                docstring=docstring,
                language="lua",
            )
        )

        body = None
        for child in node.named_children:
            if child.type == "block":
                body = child
                break
        if body:
            self._extract_calls(body, source, file_path, name, relationships)

    def _handle_variable(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # local x = value  →  assignment_statement inside
        for child in node.named_children:
            if child.type == "assignment_statement":
                lhs = child.named_children[0] if child.named_children else None
                rhs_list = child.named_children[1] if len(child.named_children) > 1 else None
                if lhs is None:
                    continue
                name = _node_text(lhs, source)
                # Check if RHS is a function expression
                if rhs_list and rhs_list.type == "expression_list":
                    for val in rhs_list.named_children:
                        if val.type == "function_definition":
                            params = None
                            for c in val.named_children:
                                if c.type == "parameters":
                                    params = c
                                    break
                            sig = f"function {name}"
                            if params:
                                sig += _node_text(params, source)
                            symbols.append(
                                Symbol(
                                    id=_build_id(file_path, name),
                                    name=name,
                                    qualified_name=name,
                                    kind=SymbolKind.FUNCTION,
                                    file_path=file_path,
                                    span=_node_span(node),
                                    signature=sig,
                                    language="lua",
                                )
                            )
                            body = None
                            for c in val.named_children:
                                if c.type == "block":
                                    body = c
                                    break
                            if body:
                                self._extract_calls(body, source, file_path, name, relationships)
                            return
                # Otherwise treat as a variable/constant
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, name),
                        name=name,
                        qualified_name=name,
                        kind=SymbolKind.VARIABLE,
                        file_path=file_path,
                        span=_node_span(node),
                        language="lua",
                    )
                )

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "function_call":
            fn_node = node.named_children[0] if node.named_children else None
            if fn_node and fn_node.type in (
                "identifier",
                "dot_index_expression",
                "method_index_expression",
            ):
                callee = _node_text(fn_node, source)
                if callee not in (
                    "print",
                    "require",
                    "pairs",
                    "ipairs",
                    "type",
                    "tostring",
                    "tonumber",
                ):
                    relationships.append(
                        Relationship(
                            source_id=_build_id(file_path, caller),
                            target_id=f"<unresolved>::{callee}",
                            kind=RelationshipKind.CALLS,
                            file_path=file_path,
                            span=_node_span(node),
                        )
                    )
        for child in node.children:
            self._extract_calls(child, source, file_path, caller, relationships)
