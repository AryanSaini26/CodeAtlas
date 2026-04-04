"""C# AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_c_sharp as tscs
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

CSHARP_LANGUAGE = Language(tscs.language())


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


def _get_xml_doc_comment(node: Node, source: bytes) -> str | None:
    """Extract preceding /// XML doc comments and return the <summary> text."""
    lines: list[str] = []
    prev = node.prev_sibling
    while prev and prev.type == "comment":
        text = _node_text(prev, source).strip()
        if text.startswith("///"):
            lines.insert(0, text[3:].strip())
            prev = prev.prev_sibling
        else:
            break
    if not lines:
        return None
    # Strip XML tags to get plain text
    import re

    joined = "\n".join(lines)
    plain = re.sub(r"<[^>]+>", "", joined).strip()
    return plain if plain else None


def _get_base_types(node: Node, source: bytes) -> list[str]:
    """Extract base type names from a base_list."""
    bases: list[str] = []
    for child in node.children:
        if child.type == "base_list":
            for inner in child.named_children:
                if inner.type in (
                    "identifier",
                    "qualified_name",
                    "generic_name",
                ):
                    bases.append(_node_text(inner, source))
            break
    return bases


def _get_modifiers(node: Node, source: bytes) -> list[str]:
    """Get modifier keywords (public, static, abstract, etc.) from a declaration."""
    return [_node_text(child, source) for child in node.children if child.type == "modifier"]


class CSharpParser(BaseParser):
    """Parses C# source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(CSHARP_LANGUAGE)

    @property
    def language(self) -> str:
        return "csharp"

    @property
    def supported_extensions(self) -> list[str]:
        return [".cs"]

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

        self._walk_children(root, source, file_path, symbols, relationships, namespace=None)

        file_info = FileInfo(
            path=file_path,
            language="csharp",
            content_hash=content_hash,
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=file_info, symbols=symbols, relationships=relationships)

    def _walk_children(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        namespace: str | None,
    ) -> None:
        for child in node.named_children:
            match child.type:
                case "using_directive":
                    self._handle_using(child, source, file_path, symbols, relationships)
                case "namespace_declaration" | "file_scoped_namespace_declaration":
                    self._handle_namespace(
                        child, source, file_path, symbols, relationships, namespace
                    )
                case "class_declaration":
                    self._handle_class(child, source, file_path, symbols, relationships, namespace)
                case "interface_declaration":
                    self._handle_interface(
                        child, source, file_path, symbols, relationships, namespace
                    )
                case "struct_declaration":
                    self._handle_struct(child, source, file_path, symbols, relationships, namespace)
                case "enum_declaration":
                    self._handle_enum(child, source, file_path, symbols, namespace)
                case "record_declaration":
                    self._handle_record(child, source, file_path, symbols, relationships, namespace)

    def _qualify(self, name: str, namespace: str | None) -> str:
        return f"{namespace}.{name}" if namespace else name

    def _handle_using(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Extract the namespace being imported
        for child in node.named_children:
            if child.type in ("identifier", "qualified_name"):
                using_name = _node_text(child, source)
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, f"using.{using_name}"),
                        name=using_name.rsplit(".", 1)[-1],
                        qualified_name=f"using.{using_name}",
                        kind=SymbolKind.IMPORT,
                        file_path=file_path,
                        span=_node_span(node),
                        language="csharp",
                    )
                )
                relationships.append(
                    Relationship(
                        source_id=_build_id(file_path, "module"),
                        target_id=f"<external>::{using_name}",
                        kind=RelationshipKind.IMPORTS,
                        file_path=file_path,
                        span=_node_span(node),
                    )
                )
                break

    def _handle_namespace(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        parent_ns: str | None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = self._qualify(name, parent_ns)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.NAMESPACE,
                file_path=file_path,
                span=_node_span(node),
                language="csharp",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._walk_children(
                body, source, file_path, symbols, relationships, namespace=qualified
            )
        else:
            # File-scoped namespace — children are direct siblings
            self._walk_children(
                node, source, file_path, symbols, relationships, namespace=qualified
            )

    def _handle_class(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        namespace: str | None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = self._qualify(name, namespace)
        docstring = _get_xml_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="csharp",
            )
        )

        for base in _get_base_types(node, source):
            kind = (
                RelationshipKind.IMPLEMENTS
                if base.startswith("I") and len(base) > 1 and base[1].isupper()
                else RelationshipKind.INHERITS
            )
            relationships.append(
                Relationship(
                    source_id=_build_id(file_path, qualified),
                    target_id=f"<unresolved>::{base}",
                    kind=kind,
                    file_path=file_path,
                    span=_node_span(node),
                )
            )

        body = node.child_by_field_name("body")
        if body:
            self._extract_members(body, source, file_path, symbols, relationships, qualified)

    def _handle_interface(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        namespace: str | None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = self._qualify(name, namespace)
        docstring = _get_xml_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.INTERFACE,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="csharp",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_members(body, source, file_path, symbols, relationships, qualified)

    def _handle_struct(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        namespace: str | None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = self._qualify(name, namespace)
        docstring = _get_xml_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="csharp",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_members(body, source, file_path, symbols, relationships, qualified)

    def _handle_enum(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        namespace: str | None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = self._qualify(name, namespace)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.ENUM,
                file_path=file_path,
                span=_node_span(node),
                language="csharp",
            )
        )

    def _handle_record(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        namespace: str | None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = self._qualify(name, namespace)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                language="csharp",
            )
        )

        for base in _get_base_types(node, source):
            relationships.append(
                Relationship(
                    source_id=_build_id(file_path, qualified),
                    target_id=f"<unresolved>::{base}",
                    kind=RelationshipKind.INHERITS,
                    file_path=file_path,
                    span=_node_span(node),
                )
            )

    def _extract_members(
        self,
        body: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str,
    ) -> None:
        """Extract methods, properties, fields, and constructors from a type body."""
        for child in body.named_children:
            match child.type:
                case "method_declaration":
                    self._handle_method(child, source, file_path, symbols, relationships, owner)
                case "constructor_declaration":
                    self._handle_constructor(
                        child, source, file_path, symbols, relationships, owner
                    )
                case "property_declaration":
                    self._handle_property(child, source, file_path, symbols, owner)
                case "field_declaration":
                    self._handle_field(child, source, file_path, symbols, owner)
                case "class_declaration":
                    # Nested class
                    self._handle_class(
                        child, source, file_path, symbols, relationships, namespace=owner
                    )
                case "interface_declaration":
                    self._handle_interface(
                        child, source, file_path, symbols, relationships, namespace=owner
                    )

    def _handle_method(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = f"{owner}.{name}"
        docstring = _get_xml_doc_comment(node, source)
        signature = self._build_method_signature(node, source, name)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.METHOD,
                file_path=file_path,
                span=_node_span(node),
                signature=signature,
                docstring=docstring,
                language="csharp",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified, relationships)

    def _handle_constructor(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = f"{owner}.{name}"

        params = node.child_by_field_name("parameters")
        sig = name
        if params:
            sig += _node_text(params, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.METHOD,
                file_path=file_path,
                span=_node_span(node),
                signature=sig,
                language="csharp",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified, relationships)

    def _handle_property(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        owner: str,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified = f"{owner}.{name}"

        type_node = node.child_by_field_name("type")
        sig = ""
        if type_node:
            sig = f"{_node_text(type_node, source)} {name}"

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.VARIABLE,
                file_path=file_path,
                span=_node_span(node),
                signature=sig if sig else None,
                language="csharp",
            )
        )

    def _handle_field(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        owner: str,
    ) -> None:
        # field_declaration -> variable_declaration -> variable_declarator
        for child in node.named_children:
            if child.type == "variable_declaration":
                for decl in child.named_children:
                    if decl.type == "variable_declarator":
                        name_node = decl.child_by_field_name("name")
                        if name_node is None:
                            continue
                        name = _node_text(name_node, source)
                        qualified = f"{owner}.{name}"

                        modifiers = _get_modifiers(node, source)
                        is_const = "const" in modifiers or (
                            "static" in modifiers and "readonly" in modifiers
                        )

                        symbols.append(
                            Symbol(
                                id=_build_id(file_path, qualified),
                                name=name,
                                qualified_name=qualified,
                                kind=SymbolKind.CONSTANT if is_const else SymbolKind.VARIABLE,
                                file_path=file_path,
                                span=_node_span(node),
                                language="csharp",
                            )
                        )

    def _build_method_signature(self, node: Node, source: bytes, name: str) -> str:
        returns = node.child_by_field_name("returns")
        params = node.child_by_field_name("parameters")
        sig = ""
        if returns:
            sig = f"{_node_text(returns, source)} "
        sig += name
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
        if node.type == "invocation_expression":
            func_node = node.child_by_field_name("function")
            if func_node:
                callee = _node_text(func_node, source)
                # For member_access_expression, get the member name with object prefix
                if func_node.type == "member_access_expression":
                    name_node = func_node.child_by_field_name("name")
                    expr_node = func_node.child_by_field_name("expression")
                    if name_node and expr_node:
                        callee = f"{_node_text(expr_node, source)}.{_node_text(name_node, source)}"
                relationships.append(
                    Relationship(
                        source_id=_build_id(file_path, caller_qualified),
                        target_id=f"<unresolved>::{callee}",
                        kind=RelationshipKind.CALLS,
                        file_path=file_path,
                        span=_node_span(node),
                    )
                )
        if node.type == "object_creation_expression":
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
