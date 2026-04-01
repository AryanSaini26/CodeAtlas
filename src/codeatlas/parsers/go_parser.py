"""Go AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_go as tsgo
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

GO_LANGUAGE = Language(tsgo.language())


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


def _get_comment(node: Node, source: bytes) -> str | None:
    """Extract a preceding comment block as a docstring."""
    prev = node.prev_sibling
    if prev and prev.type == "comment":
        text = _node_text(prev, source).lstrip("/ ").strip()
        return text or None
    return None


def _receiver_type(node: Node, source: bytes) -> str | None:
    """Extract the receiver type name from a method_declaration.

    Handles both pointer receivers (*Dog) and value receivers (Dog).
    """
    receiver = node.child_by_field_name("receiver")
    if receiver is None:
        return None
    for param in receiver.named_children:
        if param.type == "parameter_declaration":
            type_node = param.child_by_field_name("type")
            if type_node is None:
                continue
            if type_node.type == "pointer_type":
                for child in type_node.named_children:
                    if child.type == "type_identifier":
                        return _node_text(child, source)
            elif type_node.type == "type_identifier":
                return _node_text(type_node, source)
    return None


class GoParser(BaseParser):
    """Parses Go source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(GO_LANGUAGE)

    @property
    def language(self) -> str:
        return "go"

    @property
    def supported_extensions(self) -> list[str]:
        return [".go"]

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
                case "package_clause":
                    self._handle_package(child, source, file_path, symbols)
                case "import_declaration":
                    self._handle_import(child, source, file_path, symbols, relationships)
                case "function_declaration":
                    self._handle_function(child, source, file_path, symbols, relationships)
                case "method_declaration":
                    self._handle_method(child, source, file_path, symbols, relationships)
                case "type_declaration":
                    self._handle_type_decl(child, source, file_path, symbols, relationships)
                case "const_declaration":
                    self._handle_const(child, source, file_path, symbols)
                case "var_declaration":
                    self._handle_var(child, source, file_path, symbols)

        file_info = FileInfo(
            path=file_path,
            language="go",
            content_hash=content_hash,
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(
            file_info=file_info,
            symbols=symbols,
            relationships=relationships,
        )

    def _handle_package(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        for child in node.children:
            if child.type == "package_identifier":
                name = _node_text(child, source)
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, f"package.{name}"),
                        name=name,
                        qualified_name=f"package.{name}",
                        kind=SymbolKind.MODULE,
                        file_path=file_path,
                        span=_node_span(node),
                        language="go",
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
        # Single import or import block
        specs: list[Node] = []
        for child in node.children:
            if child.type == "import_spec":
                specs.append(child)
            elif child.type == "import_spec_list":
                for spec in child.named_children:
                    if spec.type == "import_spec":
                        specs.append(spec)

        for spec in specs:
            path_node = spec.child_by_field_name("path")
            if path_node is None:
                continue
            import_path = _node_text(path_node, source).strip('"')
            # Use the last segment as the short name
            short_name = import_path.rsplit("/", 1)[-1]

            # Check for alias
            alias_node = spec.child_by_field_name("name")
            if alias_node:
                short_name = _node_text(alias_node, source)

            symbols.append(
                Symbol(
                    id=_build_id(file_path, f"import.{import_path}"),
                    name=short_name,
                    qualified_name=f"import.{import_path}",
                    kind=SymbolKind.IMPORT,
                    file_path=file_path,
                    span=_node_span(spec),
                    language="go",
                )
            )
            relationships.append(
                Relationship(
                    source_id=_build_id(file_path, "module"),
                    target_id=f"<external>::{import_path}",
                    kind=RelationshipKind.IMPORTS,
                    file_path=file_path,
                    span=_node_span(spec),
                )
            )

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

        signature = self._build_signature(node, source, name)
        docstring = _get_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                span=_node_span(node),
                signature=signature,
                docstring=docstring,
                language="go",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, name, relationships)

    def _handle_method(
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

        recv_type = _receiver_type(node, source)
        qualified_name = f"{recv_type}.{name}" if recv_type else name

        signature = self._build_signature(node, source, name)
        docstring = _get_comment(node, source)

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
                language="go",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _handle_type_decl(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        for child in node.named_children:
            if child.type not in ("type_spec", "type_alias"):
                continue

            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            name = _node_text(name_node, source)

            type_node = child.child_by_field_name("type")
            if type_node is None:
                continue

            if type_node.type == "struct_type":
                kind = SymbolKind.CLASS
            elif type_node.type == "interface_type":
                kind = SymbolKind.INTERFACE
            else:
                kind = SymbolKind.TYPE_ALIAS

            docstring = _get_comment(node, source)

            symbols.append(
                Symbol(
                    id=_build_id(file_path, name),
                    name=name,
                    qualified_name=name,
                    kind=kind,
                    file_path=file_path,
                    span=_node_span(node),
                    docstring=docstring,
                    language="go",
                )
            )

            # Interface embedding (extends)
            if type_node.type == "interface_type":
                for member in type_node.named_children:
                    if member.type == "type_identifier":
                        embedded = _node_text(member, source)
                        relationships.append(
                            Relationship(
                                source_id=_build_id(file_path, name),
                                target_id=f"<unresolved>::{embedded}",
                                kind=RelationshipKind.INHERITS,
                                file_path=file_path,
                                span=_node_span(member),
                            )
                        )

            # Struct embedding
            if type_node.type == "struct_type":
                field_list = type_node.child_by_field_name("field_list") or type_node
                for field in field_list.named_children:
                    if field.type == "field_declaration":
                        # Embedded field: just a type with no name
                        has_name = field.child_by_field_name("name") is not None
                        if not has_name:
                            type_child = field.child_by_field_name("type")
                            if type_child:
                                embedded = _node_text(type_child, source).lstrip("*")
                                relationships.append(
                                    Relationship(
                                        source_id=_build_id(file_path, name),
                                        target_id=f"<unresolved>::{embedded}",
                                        kind=RelationshipKind.INHERITS,
                                        file_path=file_path,
                                        span=_node_span(field),
                                    )
                                )

    def _handle_const(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        for child in node.named_children:
            if child.type == "const_spec":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    # const_spec can have multiple names
                    for n in child.named_children:
                        if n.type == "identifier":
                            name_node = n
                            break
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
                        span=_node_span(child),
                        language="go",
                    )
                )

    def _handle_var(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        for child in node.named_children:
            if child.type == "var_spec":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    for n in child.named_children:
                        if n.type == "identifier":
                            name_node = n
                            break
                if name_node is None:
                    continue
                name = _node_text(name_node, source)
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, name),
                        name=name,
                        qualified_name=name,
                        kind=SymbolKind.VARIABLE,
                        file_path=file_path,
                        span=_node_span(child),
                        language="go",
                    )
                )

    def _build_signature(self, node: Node, source: bytes, name: str) -> str:
        params = node.child_by_field_name("parameters")
        result = node.child_by_field_name("result")
        sig = f"func {name}"
        if params:
            sig += _node_text(params, source)
        if result:
            sig += f" {_node_text(result, source)}"
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
