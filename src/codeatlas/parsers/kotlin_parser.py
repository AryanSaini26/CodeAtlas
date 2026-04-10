"""Kotlin AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_kotlin as tskotlin
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

KOTLIN_LANGUAGE = Language(tskotlin.language())


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
    while prev and prev.type in ("block_comment", "line_comment"):
        text = _node_text(prev, source).strip()
        if text.startswith("//"):
            return text.lstrip("/").strip()
        if text.startswith("/**") or text.startswith("/*"):
            inner = text.lstrip("/").lstrip("*").rstrip("*").rstrip("/").strip()
            lines = [ln.strip().lstrip("*").strip() for ln in inner.splitlines()]
            return "\n".join(ln for ln in lines if ln)
        break
    return None


def _is_interface(node: Node) -> bool:
    """Check if a class_declaration uses the 'interface' keyword."""
    for child in node.children:
        if child.type == "interface":
            return True
    return False


def _get_modifiers_text(node: Node, source: bytes) -> str:
    """Get text of the first modifiers child."""
    for child in node.named_children:
        if child.type == "modifiers":
            return _node_text(child, source)
    return ""


def _get_class_body(node: Node) -> Node | None:
    for child in node.named_children:
        if child.type == "class_body":
            return child
    return None


def _get_function_body_block(node: Node) -> Node | None:
    """Get the block node inside a function_body."""
    for child in node.named_children:
        if child.type == "function_body":
            for inner in child.named_children:
                if inner.type == "block":
                    return inner
            # expression body (= expr)
            return child
    return None


def _get_params_node(node: Node) -> Node | None:
    for child in node.named_children:
        if child.type == "function_value_parameters":
            return child
    return None


def _get_return_type(node: Node) -> Node | None:
    """Get user_type or nullable_type that follows ':' in function_declaration."""
    found_colon = False
    for child in node.children:
        if child.type == ":":
            found_colon = True
            continue
        if found_colon and child.type in ("user_type", "nullable_type", "function_type"):
            return child
        if found_colon and child.type == "function_body":
            break
    return None


class KotlinParser(BaseParser):
    """Parses Kotlin source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(KOTLIN_LANGUAGE)

    @property
    def language(self) -> str:
        return "kotlin"

    @property
    def supported_extensions(self) -> list[str]:
        return [".kt", ".kts"]

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
            language="kotlin",
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
                case "import":
                    self._handle_import(child, source, file_path, symbols, relationships)
                case "class_declaration":
                    self._handle_class(child, source, file_path, symbols, relationships)
                case "object_declaration":
                    self._handle_object(child, source, file_path, symbols, relationships)
                case "function_declaration":
                    self._handle_function(child, source, file_path, symbols, relationships, owner)
                case "property_declaration":
                    self._handle_property(child, source, file_path, symbols)

    def _handle_import(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        qi = node.named_children[0] if node.named_children else None
        if qi is None:
            return
        module = _node_text(qi, source)
        short_name = module.rsplit(".", 1)[-1]

        symbols.append(
            Symbol(
                id=_build_id(file_path, f"import.{module}"),
                name=short_name,
                qualified_name=f"import.{module}",
                kind=SymbolKind.IMPORT,
                file_path=file_path,
                span=_node_span(node),
                language="kotlin",
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
        kind = SymbolKind.INTERFACE if _is_interface(node) else SymbolKind.CLASS

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=kind,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="kotlin",
            )
        )

        # Inheritance via delegation_specifiers
        for child in node.named_children:
            if child.type == "delegation_specifiers":
                for spec in child.named_children:
                    if spec.type == "delegation_specifier":
                        parent = _node_text(spec, source).split("(")[0].strip()
                        if parent:
                            relationships.append(
                                Relationship(
                                    source_id=_build_id(file_path, name),
                                    target_id=f"<unresolved>::{parent}",
                                    kind=RelationshipKind.INHERITS,
                                    file_path=file_path,
                                    span=_node_span(node),
                                )
                            )

        # Walk class body
        body = _get_class_body(node)
        if body:
            for member in body.named_children:
                match member.type:
                    case "function_declaration":
                        self._handle_function(
                            member, source, file_path, symbols, relationships, owner=name
                        )
                    case "companion_object":
                        self._handle_companion(
                            member, source, file_path, symbols, relationships, owner=name
                        )
                    case "class_declaration":
                        self._handle_class(member, source, file_path, symbols, relationships)

    def _handle_object(
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
                language="kotlin",
            )
        )

        body = _get_class_body(node)
        if body:
            for member in body.named_children:
                if member.type == "function_declaration":
                    self._handle_function(
                        member, source, file_path, symbols, relationships, owner=name
                    )

    def _handle_companion(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str,
    ) -> None:
        body = _get_class_body(node)
        if body:
            for member in body.named_children:
                if member.type == "function_declaration":
                    self._handle_function(
                        member, source, file_path, symbols, relationships, owner=owner
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
        kind = SymbolKind.METHOD if owner else SymbolKind.FUNCTION
        docstring = _get_doc_comment(node, source)

        mod_text = _get_modifiers_text(node, source)
        params = _get_params_node(node)
        return_type = _get_return_type(node)
        sig = f"{mod_text + ' ' if mod_text else ''}fun {name}"
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
                language="kotlin",
            )
        )

        body = _get_function_body_block(node)
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _handle_property(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        var_decl = None
        for child in node.named_children:
            if child.type == "variable_declaration":
                var_decl = child
                break
        if var_decl is None:
            return
        name_node = var_decl.named_children[0] if var_decl.named_children else None
        if name_node is None:
            return
        name = _node_text(name_node, source)
        mod_text = _get_modifiers_text(node, source)
        kind = SymbolKind.CONSTANT if "const" in mod_text else SymbolKind.VARIABLE

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=kind,
                file_path=file_path,
                span=_node_span(node),
                language="kotlin",
            )
        )

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_qualified: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call_expression":
            fn = node.named_children[0] if node.named_children else None
            if fn:
                callee = _node_text(fn, source)
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
