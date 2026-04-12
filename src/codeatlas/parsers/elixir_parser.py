"""Elixir AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_elixir as tselixir
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

ELIXIR_LANGUAGE = Language(tselixir.language())

_DEF_KEYWORDS = frozenset({"def", "defp", "defmacro", "defmacrop", "defguard", "defguardp"})
_MODULE_KEYWORDS = frozenset({"defmodule", "defprotocol", "defimpl"})


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


def _call_name(node: Node, source: bytes) -> str | None:
    fn_node = node.named_children[0] if node.named_children else None
    if fn_node and fn_node.type == "identifier":
        return _node_text(fn_node, source)
    return None


def _get_doc_attr(node: Node, source: bytes) -> str | None:
    """Extract @doc string from the preceding @doc attribute in do_block."""
    prev = node.prev_sibling
    while prev:
        if prev.type == "unary_operator":
            text = _node_text(prev, source)
            if text.startswith("@doc"):
                # Strip @doc prefix and surrounding quotes
                content = text[4:].strip().strip('"').strip("'")
                if content and content != "false":
                    return content
        elif prev.type in ("newline",):
            prev = prev.prev_sibling
            continue
        break
    return None


class ElixirParser(BaseParser):
    """Parses Elixir source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(ELIXIR_LANGUAGE)

    @property
    def language(self) -> str:
        return "elixir"

    @property
    def supported_extensions(self) -> list[str]:
        return [".ex", ".exs"]

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
            language="elixir",
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
            if child.type != "call":
                continue
            kw = _call_name(child, source)
            if kw in _MODULE_KEYWORDS:
                self._handle_module(child, source, file_path, symbols, relationships)
            elif kw in _DEF_KEYWORDS:
                self._handle_def(child, source, file_path, symbols, relationships, owner)

    def _handle_module(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Arguments node holds module name (alias)
        args = node.named_children[1] if len(node.named_children) > 1 else None
        if args is None:
            return
        name_node = args.named_children[0] if args.named_children else None
        if name_node is None:
            return
        name = _node_text(name_node, source)

        kw = _call_name(node, source)
        kind = SymbolKind.INTERFACE if kw == "defprotocol" else SymbolKind.MODULE

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name.rsplit(".", 1)[-1],
                qualified_name=name,
                kind=kind,
                file_path=file_path,
                span=_node_span(node),
                language="elixir",
            )
        )

        do_block = node.named_children[2] if len(node.named_children) > 2 else None
        if do_block and do_block.type == "do_block":
            self._walk(do_block, source, file_path, symbols, relationships, owner=name)

    def _handle_def(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str | None = None,
    ) -> None:
        # def function_name(args) do ... end
        # arguments node → first child is a call (fn_name(args)) or identifier
        args_node = node.named_children[1] if len(node.named_children) > 1 else None
        if args_node is None:
            return

        # The function name is the first named child of arguments
        fn_call = args_node.named_children[0] if args_node.named_children else None
        if fn_call is None:
            return

        if fn_call.type == "call":
            # def foo(x) → fn_call is a call node with identifier + arguments
            fn_name_node = fn_call.named_children[0] if fn_call.named_children else None
            fn_args_node = fn_call.named_children[1] if len(fn_call.named_children) > 1 else None
        elif fn_call.type == "identifier":
            fn_name_node = fn_call
            fn_args_node = None
        else:
            return

        if fn_name_node is None:
            return
        fn_name = _node_text(fn_name_node, source)
        qualified_name = f"{owner}.{fn_name}" if owner else fn_name

        sig = f"def {fn_name}"
        if fn_args_node:
            sig += _node_text(fn_args_node, source)

        docstring = _get_doc_attr(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=fn_name,
                qualified_name=qualified_name,
                kind=SymbolKind.METHOD if owner else SymbolKind.FUNCTION,
                file_path=file_path,
                span=_node_span(node),
                signature=sig,
                docstring=docstring,
                language="elixir",
            )
        )

        do_block = node.named_children[2] if len(node.named_children) > 2 else None
        if do_block and do_block.type == "do_block":
            self._extract_calls(do_block, source, file_path, qualified_name, relationships)

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call":
            fn_node = node.named_children[0] if node.named_children else None
            if fn_node and fn_node.type == "identifier":
                callee = _node_text(fn_node, source)
                if callee not in _DEF_KEYWORDS and callee not in _MODULE_KEYWORDS:
                    relationships.append(
                        Relationship(
                            source_id=_build_id(file_path, caller),
                            target_id=f"<unresolved>::{callee}",
                            kind=RelationshipKind.CALLS,
                            file_path=file_path,
                            span=_node_span(node),
                        )
                    )
            elif fn_node and fn_node.type == "dot":
                callee = _node_text(fn_node, source)
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
