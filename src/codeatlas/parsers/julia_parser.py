"""Julia AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_julia as tsjulia
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

JULIA_LANGUAGE = Language(tsjulia.language())


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
    """Extract preceding # comment lines."""
    lines: list[str] = []
    prev = node.prev_sibling
    while prev and prev.type == "line_comment":
        text = _node_text(prev, source).lstrip("#").strip()
        lines.insert(0, text)
        prev = prev.prev_sibling
    return "\n".join(lines) if lines else None


class JuliaParser(BaseParser):
    """Parses Julia source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(JULIA_LANGUAGE)

    @property
    def language(self) -> str:
        return "julia"

    @property
    def supported_extensions(self) -> list[str]:
        return [".jl"]

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

        self._walk(root, source, file_path, symbols, relationships, owner=None)

        file_info = FileInfo(
            path=file_path,
            language="julia",
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
        owner: str | None,
    ) -> None:
        for child in node.named_children:
            match child.type:
                case "module_definition":
                    self._handle_module(child, source, file_path, symbols, relationships)
                case "function_definition":
                    self._handle_function(child, source, file_path, symbols, relationships, owner)
                case "struct_definition":
                    self._handle_struct(child, source, file_path, symbols)
                case "abstract_definition":
                    self._handle_abstract(child, source, file_path, symbols)
                case "macro_definition":
                    self._handle_macro(child, source, file_path, symbols)
                case "const_statement":
                    self._handle_const(child, source, file_path, symbols)
                case "import_statement" | "using_statement":
                    self._handle_import(child, source, file_path, symbols, relationships)

    def _handle_module(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = None
        for child in node.named_children:
            if child.type == "identifier":
                name_node = child
                break
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
                language="julia",
            )
        )
        # Walk module body
        self._walk(node, source, file_path, symbols, relationships, owner=name)

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str | None,
    ) -> None:
        sig_node = node.child_by_field_name("signature")
        if sig_node is None:
            sig_node = node.named_children[0] if node.named_children else None
        if sig_node is None:
            return

        # The `signature` wrapper node contains a call_expression or identifier
        call_node: Node | None = sig_node
        if sig_node.type == "signature":
            call_node = sig_node.named_children[0] if sig_node.named_children else None
        if call_node is None:
            return

        # Extract function name from call_expression or identifier
        name_node = None
        if call_node.type == "call_expression":
            name_node = call_node.named_children[0] if call_node.named_children else None
        elif call_node.type == "identifier":
            name_node = call_node

        if name_node is None:
            return

        raw_name = _node_text(name_node, source)
        # Handle qualified names like "Dog.speak" → method
        short_name = raw_name.rsplit(".", 1)[-1]
        qualified_name = f"{owner}.{short_name}" if owner and "." not in raw_name else raw_name

        docstring = _get_doc_comment(node, source)
        sig_text = _node_text(sig_node, source) if sig_node else short_name
        kind = SymbolKind.METHOD if owner and "." not in raw_name else SymbolKind.FUNCTION

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=short_name,
                qualified_name=qualified_name,
                kind=kind,
                file_path=file_path,
                span=_node_span(node),
                signature=f"function {sig_text}",
                docstring=docstring,
                language="julia",
            )
        )

        # Extract calls from function body
        for child in node.named_children:
            if child != sig_node:
                self._extract_calls(child, source, file_path, qualified_name, relationships)

    def _handle_struct(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        type_head = None
        for child in node.named_children:
            if child.type == "type_head":
                type_head = child
                break
        if type_head is None:
            return

        # type_head can be: identifier (Point) or binary_expression (Dog <: Animal)
        name_node = None
        inner = type_head.named_children[0] if type_head.named_children else None
        if inner is None:
            return
        if inner.type == "identifier":
            name_node = inner
        elif inner.type == "binary_expression":
            # First child is the struct name, second is operator, third is parent
            name_node = inner.named_children[0] if inner.named_children else None

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
                language="julia",
            )
        )

    def _handle_abstract(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        # abstract_definition → type_head → identifier  (or binary_expression for subtypes)
        type_head = None
        for child in node.named_children:
            if child.type == "type_head":
                type_head = child
                break

        name_node = None
        if type_head is not None:
            inner = type_head.named_children[0] if type_head.named_children else None
            if inner is not None:
                if inner.type == "identifier":
                    name_node = inner
                elif inner.type == "binary_expression":
                    name_node = inner.named_children[0] if inner.named_children else None
        # Fallback: first identifier child of the node itself
        if name_node is None:
            for child in node.named_children:
                if child.type == "identifier":
                    name_node = child
                    break
        if name_node is None:
            return
        name = _node_text(name_node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.INTERFACE,
                file_path=file_path,
                span=_node_span(node),
                language="julia",
            )
        )

    def _handle_macro(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        # macro signature is like a function signature: signature → call_expression → identifier
        sig_node = None
        for child in node.named_children:
            if child.type == "signature":
                sig_node = child
                break
        name_node = None
        if sig_node:
            call = sig_node.named_children[0] if sig_node.named_children else None
            if call and call.type == "call_expression":
                name_node = call.named_children[0] if call.named_children else None
        # Fallback: first identifier child
        if name_node is None:
            for child in node.named_children:
                if child.type == "identifier":
                    name_node = child
                    break
        if name_node is None:
            return
        name = _node_text(name_node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, f"@{name}"),
                name=f"@{name}",
                qualified_name=f"@{name}",
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                span=_node_span(node),
                signature=f"macro {name}",
                language="julia",
            )
        )

    def _handle_const(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        # const_statement → assignment → identifier
        for child in node.named_children:
            if child.type == "assignment":
                lhs = child.named_children[0] if child.named_children else None
                if lhs and lhs.type == "identifier":
                    name = _node_text(lhs, source)
                    symbols.append(
                        Symbol(
                            id=_build_id(file_path, name),
                            name=name,
                            qualified_name=name,
                            kind=SymbolKind.CONSTANT,
                            file_path=file_path,
                            span=_node_span(node),
                            language="julia",
                        )
                    )

    def _handle_import(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        path_text = ""
        for child in node.named_children:
            if child.type in ("identifier", "scoped_identifier"):
                path_text = _node_text(child, source)
                break
        if not path_text:
            return

        symbols.append(
            Symbol(
                id=_build_id(file_path, f"import.{path_text}"),
                name=path_text.rsplit(".", 1)[-1],
                qualified_name=f"import.{path_text}",
                kind=SymbolKind.IMPORT,
                file_path=file_path,
                span=_node_span(node),
                language="julia",
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

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call_expression":
            fn_node = node.named_children[0] if node.named_children else None
            if fn_node and fn_node.type == "identifier":
                callee = _node_text(fn_node, source)
                if callee not in ("println", "print", "typeof", "sizeof", "length"):
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
