"""Python AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_python as tspython
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

PY_LANGUAGE = Language(tspython.language())


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_docstring(node: Node, source: bytes) -> str | None:
    """Extract docstring from the first expression statement child if it's a string."""
    body = node.child_by_field_name("body")
    if body is None:
        return None
    for child in body.children:
        if child.type == "expression_statement":
            inner = child.children[0] if child.children else None
            if inner and inner.type in ("string", "concatenated_string"):
                raw = _node_text(inner, source)
                return raw.strip("\"' \t\n").strip('"""').strip("'''").strip()
    return None


def _get_decorators(node: Node, source: bytes) -> list[str]:
    decorators: list[str] = []
    for child in node.children:
        if child.type == "decorator":
            decorators.append(_node_text(child, source).lstrip("@").strip())
    return decorators


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


class PythonParser(BaseParser):
    """Parses Python source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(PY_LANGUAGE)

    @property
    def language(self) -> str:
        return "python"

    @property
    def supported_extensions(self) -> list[str]:
        return [".py"]

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
        errors: list[str] = []

        self._visit(root, source, file_path, "", symbols, relationships)

        file_info = FileInfo(
            path=file_path,
            language="python",
            content_hash=content_hash,
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(
            file_info=file_info,
            symbols=symbols,
            relationships=relationships,
            errors=errors,
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
        if node.type == "import_statement":
            self._handle_import(node, source, file_path, symbols, relationships)
        elif node.type == "import_from_statement":
            self._handle_import_from(node, source, file_path, symbols, relationships)
        elif node.type == "class_definition":
            self._handle_class(node, source, file_path, parent_name, symbols, relationships)
        elif node.type in ("function_definition", "decorated_definition"):
            self._handle_function(node, source, file_path, parent_name, symbols, relationships)
        elif node.type == "expression_statement":
            self._handle_assignment(node, source, file_path, parent_name, symbols)
        else:
            for child in node.children:
                self._visit(child, source, file_path, parent_name, symbols, relationships)

    def _handle_import(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        for child in node.named_children:
            if child.type in ("dotted_name", "aliased_import"):
                name = _node_text(child, source)
                sym = Symbol(
                    id=_build_id(file_path, f"import.{name}"),
                    name=name,
                    qualified_name=f"import.{name}",
                    kind=SymbolKind.IMPORT,
                    file_path=file_path,
                    span=_node_span(node),
                    language="python",
                )
                symbols.append(sym)
                rel = Relationship(
                    source_id=_build_id(file_path, "module"),
                    target_id=f"<external>::{name}",
                    kind=RelationshipKind.IMPORTS,
                    file_path=file_path,
                    span=_node_span(node),
                )
                relationships.append(rel)

    def _handle_import_from(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        module_node = node.child_by_field_name("module_name")
        module_name = _node_text(module_node, source) if module_node else "<unknown>"

        for child in node.named_children:
            if child.type in ("dotted_name", "aliased_import", "wildcard_import"):
                if child == module_node:
                    continue
                name = _node_text(child, source)
                full_name = f"{module_name}.{name}"
                sym = Symbol(
                    id=_build_id(file_path, f"import.{full_name}"),
                    name=name,
                    qualified_name=f"import.{full_name}",
                    kind=SymbolKind.IMPORT,
                    file_path=file_path,
                    span=_node_span(node),
                    language="python",
                )
                symbols.append(sym)
                rel = Relationship(
                    source_id=_build_id(file_path, "module"),
                    target_id=f"<external>::{full_name}",
                    kind=RelationshipKind.IMPORTS,
                    file_path=file_path,
                    span=_node_span(node),
                )
                relationships.append(rel)

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

        decorators = _get_decorators(node, source)
        docstring = _get_docstring(node, source)

        sym = Symbol(
            id=_build_id(file_path, qualified_name),
            name=name,
            qualified_name=qualified_name,
            kind=SymbolKind.CLASS,
            file_path=file_path,
            span=_node_span(node),
            docstring=docstring,
            decorators=decorators,
            language="python",
        )
        symbols.append(sym)

        # Inheritance relationships
        bases_node = node.child_by_field_name("superclasses")
        if bases_node:
            for base in bases_node.named_children:
                base_name = _node_text(base, source)
                rel = Relationship(
                    source_id=_build_id(file_path, qualified_name),
                    target_id=f"<unresolved>::{base_name}",
                    kind=RelationshipKind.INHERITS,
                    file_path=file_path,
                    span=_node_span(base),
                )
                relationships.append(rel)

        # Decorator relationships
        for dec in decorators:
            rel = Relationship(
                source_id=_build_id(file_path, qualified_name),
                target_id=f"<unresolved>::{dec}",
                kind=RelationshipKind.DECORATES,
                file_path=file_path,
            )
            relationships.append(rel)

        # Visit body
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                self._visit(child, source, file_path, qualified_name, symbols, relationships)

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Unwrap decorated_definition
        actual_node = node
        decorators: list[str] = []
        if node.type == "decorated_definition":
            decorators = _get_decorators(node, source)
            for child in node.named_children:
                if child.type in ("function_definition", "class_definition"):
                    if child.type == "class_definition":
                        self._handle_class(
                            node, source, file_path, parent_name, symbols, relationships
                        )
                        return
                    actual_node = child
                    break

        name_node = actual_node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{parent_name}.{name}" if parent_name else name

        # Determine if method or function
        kind = SymbolKind.METHOD if parent_name and "." in parent_name or (
            parent_name and not parent_name.startswith("import")
        ) else SymbolKind.FUNCTION

        # Build signature
        params_node = actual_node.child_by_field_name("parameters")
        signature = f"def {name}"
        if params_node:
            signature += _node_text(params_node, source)
        return_node = actual_node.child_by_field_name("return_type")
        if return_node:
            signature += f" -> {_node_text(return_node, source)}"

        docstring = _get_docstring(actual_node, source)
        if not decorators:
            decorators = _get_decorators(actual_node, source)

        sym = Symbol(
            id=_build_id(file_path, qualified_name),
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            file_path=file_path,
            span=_node_span(actual_node),
            docstring=docstring,
            signature=signature,
            decorators=decorators,
            language="python",
        )
        symbols.append(sym)

        # Decorator relationships
        for dec in decorators:
            rel = Relationship(
                source_id=_build_id(file_path, qualified_name),
                target_id=f"<unresolved>::{dec}",
                kind=RelationshipKind.DECORATES,
                file_path=file_path,
            )
            relationships.append(rel)

        # Extract calls from function body
        body = actual_node.child_by_field_name("body")
        if body:
            self._extract_calls(
                body, source, file_path, qualified_name, relationships
            )
            # Visit nested functions/classes
            for child in body.children:
                if child.type in ("function_definition", "decorated_definition", "class_definition"):
                    self._visit(child, source, file_path, qualified_name, symbols, relationships)

    def _handle_assignment(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_name: str,
        symbols: list[Symbol],
    ) -> None:
        # Only capture module-level UPPER_CASE constants
        if parent_name:
            return
        for child in node.children:
            if child.type == "assignment":
                lhs = child.child_by_field_name("left")
                if lhs and lhs.type == "identifier":
                    name = _node_text(lhs, source)
                    if name.isupper():
                        sym = Symbol(
                            id=_build_id(file_path, name),
                            name=name,
                            qualified_name=name,
                            kind=SymbolKind.CONSTANT,
                            file_path=file_path,
                            span=_node_span(child),
                            language="python",
                        )
                        symbols.append(sym)

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_qualified: str,
        relationships: list[Relationship],
    ) -> None:
        """Recursively find all call_expression nodes and record CALLS relationships."""
        if node.type == "call":
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
