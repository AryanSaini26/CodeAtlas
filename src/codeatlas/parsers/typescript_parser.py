"""TypeScript/TSX AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_typescript as tsts
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

TS_LANGUAGE = Language(tsts.language_typescript())
TSX_LANGUAGE = Language(tsts.language_tsx())


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


def _get_docstring(node: Node, source: bytes) -> str | None:
    """Extract a leading JSDoc comment for a node."""
    prev = node.prev_sibling
    if prev and prev.type == "comment":
        text = _node_text(prev, source).strip()
        if text.startswith("/**"):
            # Strip /** ... */ markers and leading * on each line
            lines = text[3:-2].splitlines()
            cleaned = []
            for line in lines:
                stripped = line.strip().lstrip("* ").strip()
                if stripped:
                    cleaned.append(stripped)
            return " ".join(cleaned).strip() or None
    return None


class TypeScriptParser(BaseParser):
    """Parses TypeScript and TSX source files using tree-sitter."""

    def __init__(self) -> None:
        self._ts_parser = Parser(TS_LANGUAGE)
        self._tsx_parser = Parser(TSX_LANGUAGE)

    @property
    def language(self) -> str:
        return "typescript"

    @property
    def supported_extensions(self) -> list[str]:
        return [".ts", ".tsx"]

    def parse_file(self, path: Path) -> ParseResult:
        source = path.read_bytes()
        return self._parse(source, str(path), is_tsx=path.suffix == ".tsx")

    def parse_source(self, source: str, file_path: str) -> ParseResult:
        is_tsx = file_path.endswith(".tsx")
        return self._parse(source.encode("utf-8"), file_path, is_tsx=is_tsx)

    def _parse(self, source: bytes, file_path: str, is_tsx: bool = False) -> ParseResult:
        content_hash = hashlib.sha256(source).hexdigest()
        parser = self._tsx_parser if is_tsx else self._ts_parser
        tree = parser.parse(source)
        root = tree.root_node

        symbols: list[Symbol] = []
        relationships: list[Relationship] = []

        self._visit(root, source, file_path, "", symbols, relationships)

        file_info = FileInfo(
            path=file_path,
            language="typescript",
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

    def _visit(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        match node.type:
            case "import_statement":
                self._handle_import(node, source, file_path, relationships)
            case "export_statement":
                self._handle_export(node, source, file_path, parent_name, symbols, relationships)
            case "function_declaration" | "generator_function_declaration":
                self._handle_function_decl(node, source, file_path, parent_name, symbols, relationships)
            case "class_declaration":
                self._handle_class(node, source, file_path, parent_name, symbols, relationships)
            case "interface_declaration":
                self._handle_interface(node, source, file_path, parent_name, symbols, relationships)
            case "type_alias_declaration":
                self._handle_type_alias(node, source, file_path, parent_name, symbols)
            case "enum_declaration":
                self._handle_enum(node, source, file_path, parent_name, symbols)
            case "lexical_declaration" | "variable_declaration":
                self._handle_variable_decl(node, source, file_path, parent_name, symbols, relationships)
            case "module" | "internal_module":
                self._handle_namespace(node, source, file_path, parent_name, symbols, relationships)
            case _:
                for child in node.children:
                    self._visit(child, source, file_path, parent_name, symbols, relationships)

    def _handle_import(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        relationships: list[Relationship],
    ) -> None:
        # Find the module specifier (the string after 'from')
        source_node = node.child_by_field_name("source")
        if source_node is None:
            for child in node.children:
                if child.type == "string":
                    source_node = child
                    break
        module_name = _node_text(source_node, source).strip("'\"")\
            if source_node else "<unknown>"

        # Named imports: { foo, bar }
        for child in node.children:
            if child.type == "import_clause":
                for inner in child.children:
                    if inner.type == "named_imports":
                        for spec in inner.named_children:
                            if spec.type == "import_specifier":
                                name_node = spec.child_by_field_name("name") or spec.children[0]
                                name = _node_text(name_node, source)
                                rel = Relationship(
                                    source_id=_build_id(file_path, "module"),
                                    target_id=f"<external>::{module_name}.{name}",
                                    kind=RelationshipKind.IMPORTS,
                                    file_path=file_path,
                                    span=_node_span(node),
                                )
                                relationships.append(rel)
                    elif inner.type == "identifier":
                        # default import
                        name = _node_text(inner, source)
                        rel = Relationship(
                            source_id=_build_id(file_path, "module"),
                            target_id=f"<external>::{module_name}.default",
                            kind=RelationshipKind.IMPORTS,
                            file_path=file_path,
                            span=_node_span(node),
                        )
                        relationships.append(rel)
                    elif inner.type == "namespace_import":
                        rel = Relationship(
                            source_id=_build_id(file_path, "module"),
                            target_id=f"<external>::{module_name}.*",
                            kind=RelationshipKind.IMPORTS,
                            file_path=file_path,
                            span=_node_span(node),
                        )
                        relationships.append(rel)

    def _handle_export(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        """Unwrap export statements and delegate to the appropriate handler."""
        for child in node.children:
            match child.type:
                case "function_declaration" | "generator_function_declaration":
                    self._handle_function_decl(child, source, file_path, parent_name, symbols, relationships)
                case "class_declaration":
                    self._handle_class(child, source, file_path, parent_name, symbols, relationships)
                case "interface_declaration":
                    self._handle_interface(child, source, file_path, parent_name, symbols, relationships)
                case "type_alias_declaration":
                    self._handle_type_alias(child, source, file_path, parent_name, symbols)
                case "enum_declaration":
                    self._handle_enum(child, source, file_path, parent_name, symbols)
                case "lexical_declaration" | "variable_declaration":
                    self._handle_variable_decl(child, source, file_path, parent_name, symbols, relationships)
                case "internal_module":
                    self._handle_namespace(child, source, file_path, parent_name, symbols, relationships)
                case "export_clause":
                    # re-exports: export { foo, bar } from './module'
                    source_node = node.child_by_field_name("source")
                    module_name = _node_text(source_node, source).strip("'\"") if source_node else None
                    if module_name:
                        for spec in child.named_children:
                            if spec.type == "export_specifier":
                                n = spec.child_by_field_name("name") or spec.children[0]
                                rel = Relationship(
                                    source_id=_build_id(file_path, "module"),
                                    target_id=f"<external>::{module_name}.{_node_text(n, source)}",
                                    kind=RelationshipKind.IMPORTS,
                                    file_path=file_path,
                                    span=_node_span(node),
                                )
                                relationships.append(rel)

    def _handle_function_decl(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{parent_name}.{name}" if parent_name else name

        kind = SymbolKind.METHOD if parent_name else SymbolKind.FUNCTION
        signature = self._build_function_signature(node, source, name)
        docstring = _get_docstring(node, source)

        sym = Symbol(
            id=_build_id(file_path, qualified_name),
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            file_path=file_path,
            span=_node_span(node),
            signature=signature,
            docstring=docstring,
            language="typescript",
        )
        symbols.append(sym)

        # Extract calls from body
        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _handle_class(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{parent_name}.{name}" if parent_name else name

        docstring = _get_docstring(node, source)

        sym = Symbol(
            id=_build_id(file_path, qualified_name),
            name=name,
            qualified_name=qualified_name,
            kind=SymbolKind.CLASS,
            file_path=file_path,
            span=_node_span(node),
            docstring=docstring,
            language="typescript",
        )
        symbols.append(sym)

        # Inheritance: extends clause
        heritage = node.child_by_field_name("heritage") or self._find_child(node, "class_heritage")
        if heritage:
            for clause in heritage.children:
                if clause.type == "extends_clause":
                    for base in clause.named_children:
                        base_name = _node_text(base, source)
                        if base_name not in ("extends",):
                            rel = Relationship(
                                source_id=_build_id(file_path, qualified_name),
                                target_id=f"<unresolved>::{base_name}",
                                kind=RelationshipKind.INHERITS,
                                file_path=file_path,
                                span=_node_span(clause),
                            )
                            relationships.append(rel)
                elif clause.type == "implements_clause":
                    for iface in clause.named_children:
                        iface_name = _node_text(iface, source)
                        if iface_name not in ("implements",):
                            rel = Relationship(
                                source_id=_build_id(file_path, qualified_name),
                                target_id=f"<unresolved>::{iface_name}",
                                kind=RelationshipKind.IMPLEMENTS,
                                file_path=file_path,
                                span=_node_span(clause),
                            )
                            relationships.append(rel)

        # Visit class body for methods
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type in ("method_definition", "public_field_definition"):
                    self._handle_class_member(child, source, file_path, qualified_name, symbols, relationships)

    def _handle_class_member(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        class_qualified: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{class_qualified}.{name}"

        if node.type == "method_definition":
            signature = self._build_function_signature(node, source, name)
            kind = SymbolKind.METHOD
            sym = Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=kind,
                file_path=file_path,
                span=_node_span(node),
                signature=signature,
                docstring=_get_docstring(node, source),
                language="typescript",
            )
            symbols.append(sym)
            body = node.child_by_field_name("body")
            if body:
                self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _handle_interface(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{parent_name}.{name}" if parent_name else name

        sym = Symbol(
            id=_build_id(file_path, qualified_name),
            name=name,
            qualified_name=qualified_name,
            kind=SymbolKind.INTERFACE,
            file_path=file_path,
            span=_node_span(node),
            docstring=_get_docstring(node, source),
            language="typescript",
        )
        symbols.append(sym)

        # extends clause on interface
        for child in node.children:
            if child.type == "extends_type_clause":
                for base in child.named_children:
                    base_name = _node_text(base, source)
                    rel = Relationship(
                        source_id=_build_id(file_path, qualified_name),
                        target_id=f"<unresolved>::{base_name}",
                        kind=RelationshipKind.INHERITS,
                        file_path=file_path,
                        span=_node_span(child),
                    )
                    relationships.append(rel)

    def _handle_type_alias(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{parent_name}.{name}" if parent_name else name

        sym = Symbol(
            id=_build_id(file_path, qualified_name),
            name=name,
            qualified_name=qualified_name,
            kind=SymbolKind.TYPE_ALIAS,
            file_path=file_path,
            span=_node_span(node),
            language="typescript",
        )
        symbols.append(sym)

    def _handle_enum(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{parent_name}.{name}" if parent_name else name

        sym = Symbol(
            id=_build_id(file_path, qualified_name),
            name=name,
            qualified_name=qualified_name,
            kind=SymbolKind.ENUM,
            file_path=file_path,
            span=_node_span(node),
            language="typescript",
        )
        symbols.append(sym)

    def _handle_variable_decl(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        for declarator in node.named_children:
            if declarator.type != "variable_declarator":
                continue
            name_node = declarator.child_by_field_name("name")
            if name_node is None:
                continue

            # Skip destructuring patterns for now
            if name_node.type not in ("identifier",):
                continue

            name = _node_text(name_node, source)
            qualified_name = f"{parent_name}.{name}" if parent_name else name

            # Check if the value is an arrow function or function expression
            value_node = declarator.child_by_field_name("value")
            if value_node and value_node.type in ("arrow_function", "function_expression", "generator_function"):
                signature = self._build_function_signature(value_node, source, name)
                kind = SymbolKind.METHOD if parent_name else SymbolKind.FUNCTION
                sym = Symbol(
                    id=_build_id(file_path, qualified_name),
                    name=name,
                    qualified_name=qualified_name,
                    kind=kind,
                    file_path=file_path,
                    span=_node_span(declarator),
                    signature=signature,
                    docstring=_get_docstring(node, source),
                    language="typescript",
                )
                symbols.append(sym)
                body = value_node.child_by_field_name("body")
                if body:
                    self._extract_calls(body, source, file_path, qualified_name, relationships)
            elif not parent_name:
                # Module-level constants/variables
                kind = SymbolKind.CONSTANT if name.isupper() else SymbolKind.VARIABLE
                sym = Symbol(
                    id=_build_id(file_path, qualified_name),
                    name=name,
                    qualified_name=qualified_name,
                    kind=kind,
                    file_path=file_path,
                    span=_node_span(declarator),
                    language="typescript",
                )
                symbols.append(sym)

    def _handle_namespace(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{parent_name}.{name}" if parent_name else name

        sym = Symbol(
            id=_build_id(file_path, qualified_name),
            name=name,
            qualified_name=qualified_name,
            kind=SymbolKind.NAMESPACE,
            file_path=file_path,
            span=_node_span(node),
            language="typescript",
        )
        symbols.append(sym)

        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                self._visit(child, source, file_path, qualified_name, symbols, relationships)

    def _build_function_signature(self, node: Node, source: bytes, name: str) -> str:
        params_node = node.child_by_field_name("parameters")
        return_node = node.child_by_field_name("return_type")
        type_params = node.child_by_field_name("type_parameters")

        sig = name
        if type_params:
            sig += _node_text(type_params, source)
        if params_node:
            sig += _node_text(params_node, source)
        if return_node:
            sig += _node_text(return_node, source)
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
                rel = Relationship(
                    source_id=_build_id(file_path, caller_qualified),
                    target_id=f"<unresolved>::{callee}",
                    kind=RelationshipKind.CALLS,
                    file_path=file_path,
                    span=_node_span(node),
                )
                relationships.append(rel)
        for child in node.children:
            self._extract_calls(child, source, file_path, caller_qualified, relationships)

    def _find_child(self, node: Node, child_type: str) -> Node | None:
        for child in node.children:
            if child.type == child_type:
                return child
        return None
