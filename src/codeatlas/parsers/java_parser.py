"""Java AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_java as tsjava
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

JAVA_LANGUAGE = Language(tsjava.language())


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


def _get_javadoc(node: Node, source: bytes) -> str | None:
    """Extract a preceding Javadoc or block comment."""
    prev = node.prev_sibling
    if prev and prev.type == "block_comment":
        text = _node_text(prev, source)
        # Strip /** ... */ markers and leading * on each line
        lines = text.strip("/ *\n").split("\n")
        cleaned = [line.strip().lstrip("* ").strip() for line in lines]
        result = " ".join(line for line in cleaned if line)
        return result or None
    if prev and prev.type == "line_comment":
        text = _node_text(prev, source).lstrip("/ ").strip()
        return text or None
    return None


def _get_annotations(node: Node, source: bytes) -> list[str]:
    """Extract annotation names from a node's modifiers."""
    annotations: list[str] = []
    for child in node.children:
        if child.type == "modifiers":
            for mod in child.children:
                if mod.type in ("marker_annotation", "annotation"):
                    name_node = mod.child_by_field_name("name")
                    if name_node:
                        annotations.append(f"@{_node_text(name_node, source)}")
                    else:
                        annotations.append(_node_text(mod, source))
    return annotations


class JavaParser(BaseParser):
    """Parses Java source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(JAVA_LANGUAGE)

    @property
    def language(self) -> str:
        return "java"

    @property
    def supported_extensions(self) -> list[str]:
        return [".java"]

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
                case "package_declaration":
                    self._handle_package(child, source, file_path, symbols)
                case "import_declaration":
                    self._handle_import(child, source, file_path, symbols, relationships)
                case "class_declaration":
                    self._handle_class(child, source, file_path, symbols, relationships)
                case "interface_declaration":
                    self._handle_interface(child, source, file_path, symbols, relationships)
                case "enum_declaration":
                    self._handle_enum(child, source, file_path, symbols)
                case "record_declaration":
                    self._handle_record(child, source, file_path, symbols)

        file_info = FileInfo(
            path=file_path,
            language="java",
            content_hash=content_hash,
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=file_info, symbols=symbols, relationships=relationships)

    def _handle_package(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        # Extract the package name from the scoped_identifier child
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier"):
                name = _node_text(child, source)
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, f"package.{name}"),
                        name=name,
                        qualified_name=f"package.{name}",
                        kind=SymbolKind.MODULE,
                        file_path=file_path,
                        span=_node_span(node),
                        language="java",
                    )
                )
                break

    def _handle_import(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Get the full import path
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier"):
                import_path = _node_text(child, source)
                short_name = import_path.rsplit(".", 1)[-1]

                symbols.append(
                    Symbol(
                        id=_build_id(file_path, f"import.{import_path}"),
                        name=short_name,
                        qualified_name=f"import.{import_path}",
                        kind=SymbolKind.IMPORT,
                        file_path=file_path,
                        span=_node_span(node),
                        language="java",
                    )
                )
                relationships.append(
                    Relationship(
                        source_id=_build_id(file_path, "module"),
                        target_id=f"<external>::{import_path}",
                        kind=RelationshipKind.IMPORTS,
                        file_path=file_path,
                        span=_node_span(node),
                    )
                )
                break

    def _handle_class(
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
        docstring = _get_javadoc(node, source)
        decorators = _get_annotations(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                decorators=decorators,
                language="java",
            )
        )

        # extends
        superclass = node.child_by_field_name("superclass")
        if superclass:
            for child in superclass.children:
                if child.type == "type_identifier":
                    parent_name = _node_text(child, source)
                    relationships.append(
                        Relationship(
                            source_id=_build_id(file_path, qualified_name),
                            target_id=f"<unresolved>::{parent_name}",
                            kind=RelationshipKind.INHERITS,
                            file_path=file_path,
                            span=_node_span(child),
                        )
                    )

        # implements
        interfaces = node.child_by_field_name("interfaces")
        if interfaces:
            for child in interfaces.children:
                if child.type == "type_list":
                    for type_node in child.named_children:
                        iface_name = _node_text(type_node, source)
                        relationships.append(
                            Relationship(
                                source_id=_build_id(file_path, qualified_name),
                                target_id=f"<unresolved>::{iface_name}",
                                kind=RelationshipKind.IMPLEMENTS,
                                file_path=file_path,
                                span=_node_span(type_node),
                            )
                        )

        # Process class body
        body = node.child_by_field_name("body")
        if body:
            self._process_class_body(
                body, source, file_path, qualified_name, symbols, relationships
            )

    def _handle_interface(
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
        docstring = _get_javadoc(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=SymbolKind.INTERFACE,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="java",
            )
        )

        # Interface extends
        for child in node.children:
            if child.type == "extends_interfaces":
                for type_list in child.children:
                    if type_list.type == "type_list":
                        for type_node in type_list.named_children:
                            parent = _node_text(type_node, source)
                            relationships.append(
                                Relationship(
                                    source_id=_build_id(file_path, qualified_name),
                                    target_id=f"<unresolved>::{parent}",
                                    kind=RelationshipKind.INHERITS,
                                    file_path=file_path,
                                    span=_node_span(type_node),
                                )
                            )

        # Interface methods
        body = node.child_by_field_name("body")
        if body:
            for child in body.named_children:
                if child.type == "method_declaration":
                    self._handle_method(
                        child, source, file_path, qualified_name, symbols, relationships
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
        docstring = _get_javadoc(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.ENUM,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="java",
            )
        )

    def _handle_record(
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
        docstring = _get_javadoc(node, source)

        # Build signature from formal parameters
        params = node.child_by_field_name("parameters")
        sig = f"record {name}"
        if params:
            sig += _node_text(params, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                signature=sig,
                docstring=docstring,
                language="java",
            )
        )

    def _process_class_body(
        self,
        body: Node,
        source: bytes,
        file_path: str,
        class_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        for child in body.named_children:
            match child.type:
                case "method_declaration":
                    self._handle_method(
                        child, source, file_path, class_name, symbols, relationships
                    )
                case "constructor_declaration":
                    self._handle_constructor(
                        child, source, file_path, class_name, symbols, relationships
                    )
                case "field_declaration":
                    self._handle_field(child, source, file_path, class_name, symbols)
                case "class_declaration":
                    self._handle_class(
                        child, source, file_path, symbols, relationships, owner=class_name
                    )
                case "interface_declaration":
                    self._handle_interface(
                        child, source, file_path, symbols, relationships, owner=class_name
                    )

    def _handle_method(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        class_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{class_name}.{name}"
        docstring = _get_javadoc(node, source)
        decorators = _get_annotations(node, source)

        signature = self._build_method_signature(node, source, name)

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
                decorators=decorators,
                language="java",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _handle_constructor(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        class_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{class_name}.{name}"

        params = node.child_by_field_name("parameters")
        sig = name
        if params:
            sig += _node_text(params, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=SymbolKind.METHOD,
                file_path=file_path,
                span=_node_span(node),
                signature=sig,
                language="java",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _handle_field(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        class_name: str,
        symbols: list[Symbol],
    ) -> None:
        # Find the variable declarator(s)
        for child in node.named_children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                name = _node_text(name_node, source)
                qualified_name = f"{class_name}.{name}"

                # Check if it's a constant (static final)
                is_constant = False
                for mod_child in node.children:
                    if mod_child.type == "modifiers":
                        mod_text = _node_text(mod_child, source)
                        if "static" in mod_text and "final" in mod_text:
                            is_constant = True
                            break

                symbols.append(
                    Symbol(
                        id=_build_id(file_path, qualified_name),
                        name=name,
                        qualified_name=qualified_name,
                        kind=SymbolKind.CONSTANT if is_constant else SymbolKind.VARIABLE,
                        file_path=file_path,
                        span=_node_span(node),
                        language="java",
                    )
                )

    def _build_method_signature(self, node: Node, source: bytes, name: str) -> str:
        # Get return type
        type_node = node.child_by_field_name("type")
        return_type = _node_text(type_node, source) if type_node else "void"
        params = node.child_by_field_name("parameters")
        sig = f"{return_type} {name}"
        if params:
            sig += _node_text(params, source)
        return sig

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_qualified: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            if name_node:
                # Include object if present: obj.method
                obj_node = node.child_by_field_name("object")
                if obj_node:
                    callee = f"{_node_text(obj_node, source)}.{_node_text(name_node, source)}"
                else:
                    callee = _node_text(name_node, source)
                relationships.append(
                    Relationship(
                        source_id=_build_id(file_path, caller_qualified),
                        target_id=f"<unresolved>::{callee}",
                        kind=RelationshipKind.CALLS,
                        file_path=file_path,
                        span=_node_span(node),
                    )
                )
        elif node.type == "object_creation_expression":
            type_node = node.child_by_field_name("type")
            if type_node:
                callee = _node_text(type_node, source)
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
