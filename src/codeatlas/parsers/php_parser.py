"""PHP AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_php as tsphp
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

PHP_LANGUAGE = Language(tsphp.language_php())


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
    while prev and prev.type == "comment":
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


def _get_name(node: Node, source: bytes) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    return _node_text(name_node, source)


def _is_static(node: Node, source: bytes) -> bool:
    for child in node.named_children:
        if child.type == "static_modifier":
            return True
    return False


class PhpParser(BaseParser):
    """Parses PHP source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(PHP_LANGUAGE)

    @property
    def language(self) -> str:
        return "php"

    @property
    def supported_extensions(self) -> list[str]:
        return [".php"]

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
            language="php",
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
                case "namespace_use_declaration":
                    self._handle_use(child, source, file_path, symbols, relationships)
                case "const_declaration":
                    self._handle_const(child, source, file_path, symbols)
                case "interface_declaration":
                    self._handle_interface(child, source, file_path, symbols, relationships)
                case "class_declaration" | "abstract_class_declaration":
                    self._handle_class(child, source, file_path, symbols, relationships)
                case "trait_declaration":
                    self._handle_trait(child, source, file_path, symbols, relationships)
                case "function_definition":
                    self._handle_function(child, source, file_path, symbols, relationships, owner)
                case "namespace_definition":
                    # Recurse into namespace body if present
                    body = child.child_by_field_name("body")
                    if body:
                        self._walk(body, source, file_path, symbols, relationships, owner)

    def _handle_use(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        for clause in node.named_children:
            if clause.type == "namespace_use_clause":
                module = _node_text(clause, source).strip()
                short_name = module.rsplit("\\", 1)[-1]
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, f"use.{module}"),
                        name=short_name,
                        qualified_name=f"use.{module}",
                        kind=SymbolKind.IMPORT,
                        file_path=file_path,
                        span=_node_span(node),
                        language="php",
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

    def _handle_const(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        for elem in node.named_children:
            if elem.type == "const_element":
                name_node = elem.named_children[0] if elem.named_children else None
                if name_node is None:
                    continue
                name = _node_text(name_node, source)
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, name),
                        name=name,
                        qualified_name=name,
                        kind=SymbolKind.CONSTANT,
                        file_path=file_path,
                        span=_node_span(elem),
                        language="php",
                    )
                )

    def _handle_interface(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name = _get_name(node, source)
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
                language="php",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                if member.type == "method_declaration":
                    self._handle_method(member, source, file_path, symbols, relationships, name)

    def _handle_class(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name = _get_name(node, source)
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
                language="php",
            )
        )

        # Inheritance
        for child in node.named_children:
            if child.type == "base_clause":
                # base_clause has 'extends' keyword + 'name' node (not a field)
                parent_name = next(
                    (_node_text(c, source) for c in child.named_children if c.type == "name"),
                    None,
                )
                if parent_name:
                    relationships.append(
                        Relationship(
                            source_id=_build_id(file_path, name),
                            target_id=f"<unresolved>::{parent_name}",
                            kind=RelationshipKind.INHERITS,
                            file_path=file_path,
                            span=_node_span(node),
                        )
                    )

        # Interfaces implemented
        iface_clause = node.child_by_field_name("interfaces")
        if iface_clause is None:
            # try 'class_interface_clause'
            for child in node.named_children:
                if child.type == "class_interface_clause":
                    iface_clause = child
                    break
        if iface_clause:
            for iface_name_node in iface_clause.named_children:
                if iface_name_node.type == "name":
                    iface = _node_text(iface_name_node, source)
                    relationships.append(
                        Relationship(
                            source_id=_build_id(file_path, name),
                            target_id=f"<unresolved>::{iface}",
                            kind=RelationshipKind.IMPLEMENTS,
                            file_path=file_path,
                            span=_node_span(node),
                        )
                    )

        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                if member.type == "method_declaration":
                    self._handle_method(member, source, file_path, symbols, relationships, name)

    def _handle_trait(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name = _get_name(node, source)
        if name is None:
            return

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                language="php",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                if member.type == "method_declaration":
                    self._handle_method(member, source, file_path, symbols, relationships, name)

    def _handle_method(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str,
    ) -> None:
        name = _get_name(node, source)
        if name is None:
            return
        qualified_name = f"{owner}.{name}"
        docstring = _get_doc_comment(node, source)
        is_static_method = _is_static(node, source)

        params = node.child_by_field_name("parameters")
        return_type = node.child_by_field_name("return_type")
        static_prefix = "static " if is_static_method else ""
        sig = f"{static_prefix}function {name}"
        if params:
            sig += _node_text(params, source)
        if return_type:
            sig += f": {_node_text(return_type, source)}"

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=SymbolKind.METHOD,
                file_path=file_path,
                span=_node_span(node),
                signature=sig,
                docstring=docstring,
                language="php",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str | None = None,
    ) -> None:
        name = _get_name(node, source)
        if name is None:
            return
        qualified_name = f"{owner}.{name}" if owner else name
        docstring = _get_doc_comment(node, source)

        params = node.child_by_field_name("parameters")
        return_type = node.child_by_field_name("return_type")
        sig = f"function {name}"
        if params:
            sig += _node_text(params, source)
        if return_type:
            sig += f": {_node_text(return_type, source)}"

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                span=_node_span(node),
                signature=sig,
                docstring=docstring,
                language="php",
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
        if node.type in (
            "function_call_expression",
            "scoped_call_expression",
            "member_call_expression",
            "object_creation_expression",
        ):
            fn_node = node.child_by_field_name("function")
            if fn_node is None:
                # scoped: scope::name, member: object->name
                scope = node.child_by_field_name("scope") or node.child_by_field_name("object")
                name_field = node.child_by_field_name("name")
                class_node = node.child_by_field_name("class")
                if scope and name_field:
                    callee = f"{_node_text(scope, source)}::{_node_text(name_field, source)}"
                elif class_node:
                    callee = _node_text(class_node, source)
                else:
                    callee = None
            else:
                callee = _node_text(fn_node, source)

            if callee:
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
