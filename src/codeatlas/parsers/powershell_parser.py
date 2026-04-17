"""PowerShell AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_powershell as tsps
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

POWERSHELL_LANGUAGE = Language(tsps.language())

# Common PowerShell cmdlets to skip when recording calls
_PS_BUILTINS = frozenset(
    {
        "Write-Host",
        "Write-Output",
        "Write-Error",
        "Write-Verbose",
        "Write-Warning",
        "Write-Debug",
        "Get-Item",
        "Set-Item",
        "Remove-Item",
        "Get-Content",
        "Set-Content",
        "Out-File",
        "Format-Table",
        "Format-List",
        "Select-Object",
        "Where-Object",
        "ForEach-Object",
        "Sort-Object",
        "Invoke-Expression",
        "Import-Module",
        "Export-ModuleMember",
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
    """Extract preceding # comment lines.

    In PowerShell, function_statement is inside a statement_list. The comment
    may be a sibling of the parent statement_list rather than the function node.
    """
    lines: list[str] = []
    # Try direct prev_sibling first
    prev = node.prev_sibling
    # Fall back to parent's prev_sibling when function is first in its block
    if prev is None and node.parent is not None:
        prev = node.parent.prev_sibling
    while prev and prev.type == "comment":
        text = _node_text(prev, source).lstrip("#").strip()
        lines.insert(0, text)
        prev = prev.prev_sibling
    return "\n".join(lines) if lines else None


class PowerShellParser(BaseParser):
    """Parses PowerShell source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(POWERSHELL_LANGUAGE)

    @property
    def language(self) -> str:
        return "powershell"

    @property
    def supported_extensions(self) -> list[str]:
        return [".ps1", ".psm1", ".psd1"]

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
            language="powershell",
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
                case "function_statement":
                    self._handle_function(child, source, file_path, symbols, relationships)
                case "class_statement":
                    self._handle_class(child, source, file_path, symbols, relationships)
                case _:
                    self._walk(child, source, file_path, symbols, relationships)

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str | None = None,
    ) -> None:
        name_node = node.child_by_field_name("function_name")
        if name_node is None:
            for child in node.named_children:
                if child.type == "function_name":
                    name_node = child
                    break
        if name_node is None:
            return

        name = _node_text(name_node, source)
        qualified_name = f"{owner}.{name}" if owner else name
        docstring = _get_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=SymbolKind.METHOD if owner else SymbolKind.FUNCTION,
                file_path=file_path,
                span=_node_span(node),
                signature=f"function {name}",
                docstring=docstring,
                language="powershell",
            )
        )

        # Extract calls from function body
        for child in node.named_children:
            if child.type == "script_block":
                self._extract_calls(child, source, file_path, qualified_name, relationships)

    def _handle_class(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = None
        for child in node.named_children:
            if child.type == "simple_name":
                name_node = child
                break
        if name_node is None:
            return

        class_name = _node_text(name_node, source)
        docstring = _get_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, class_name),
                name=class_name,
                qualified_name=class_name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="powershell",
            )
        )

        # Extract methods from class body
        for child in node.named_children:
            if child.type == "class_method_definition":
                self._handle_class_method(
                    child, source, file_path, symbols, relationships, class_name
                )

    def _handle_class_method(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str,
    ) -> None:
        # Method name is in a simple_name child
        name_node = None
        for child in node.named_children:
            if child.type == "simple_name":
                name_node = child
                break
        if name_node is None:
            return

        method_name = _node_text(name_node, source)
        qualified_name = f"{owner}.{method_name}"

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=method_name,
                qualified_name=qualified_name,
                kind=SymbolKind.METHOD,
                file_path=file_path,
                span=_node_span(node),
                signature=f"{owner}.{method_name}()",
                language="powershell",
            )
        )

        for child in node.named_children:
            if child.type == "script_block":
                self._extract_calls(child, source, file_path, qualified_name, relationships)

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "command":
            name_nodes = [c for c in node.named_children if c.type == "command_name"]
            if name_nodes:
                callee = _node_text(name_nodes[0], source)
                if callee and callee not in _PS_BUILTINS and not callee.startswith("$"):
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
