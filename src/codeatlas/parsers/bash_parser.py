"""Bash/Shell AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_bash as tsbash
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

BASH_LANGUAGE = Language(tsbash.language())

# Shell builtins and common commands that are not user-defined calls
_SHELL_BUILTINS = frozenset(
    {
        "echo",
        "printf",
        "read",
        "exit",
        "return",
        "export",
        "local",
        "declare",
        "typeset",
        "set",
        "unset",
        "shift",
        "source",
        ".",
        "eval",
        "exec",
        "cd",
        "pwd",
        "test",
        "[",
        "[[",
        "if",
        "then",
        "else",
        "fi",
        "for",
        "while",
        "do",
        "done",
        "case",
        "esac",
        "true",
        "false",
        "mkdir",
        "rm",
        "mv",
        "cp",
        "cat",
        "grep",
        "sed",
        "awk",
        "sort",
        "cut",
        "tr",
        "wc",
    }
)


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
    """Extract preceding # comment line."""
    prev = node.prev_sibling
    while prev and prev.type == "comment":
        text = _node_text(prev, source).lstrip("#").strip()
        return text
    return None


class BashParser(BaseParser):
    """Parses Bash/Shell source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(BASH_LANGUAGE)

    @property
    def language(self) -> str:
        return "bash"

    @property
    def supported_extensions(self) -> list[str]:
        return [".sh", ".bash"]

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
            language="bash",
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
            if child.type == "function_definition":
                self._handle_function(child, source, file_path, symbols, relationships)
            elif child.type == "variable_assignment":
                self._handle_variable(child, source, file_path, symbols)

    def _handle_function(
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
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                span=_node_span(node),
                signature=f"function {name}()",
                docstring=docstring,
                language="bash",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, name, relationships)

    def _handle_variable(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        name_node = node.named_children[0] if node.named_children else None
        if name_node is None or name_node.type != "variable_name":
            return
        name = _node_text(name_node, source)
        # Only capture UPPER_CASE as constants, skip lowercase internal vars
        if not name.isupper():
            return

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CONSTANT,
                file_path=file_path,
                span=_node_span(node),
                language="bash",
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
        if node.type == "command":
            name_node = node.named_children[0] if node.named_children else None
            if name_node and name_node.type in ("word", "command_name"):
                callee = _node_text(name_node, source)
                if callee and callee not in _SHELL_BUILTINS and not callee.startswith("$"):
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
