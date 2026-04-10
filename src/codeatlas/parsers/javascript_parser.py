"""JavaScript AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_javascript as tsjs
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

JS_LANGUAGE = Language(tsjs.language())


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


def _get_jsdoc(node: Node, source: bytes) -> str | None:
    """Extract preceding // or /** */ comment as docstring."""
    prev = node.prev_sibling
    # Skip whitespace-only text nodes
    while prev and prev.type in ("comment", "block_comment"):
        text = _node_text(prev, source).strip()
        if text.startswith("//"):
            return text.lstrip("/").strip()
        if text.startswith("/**") or text.startswith("/*"):
            # Strip /* */ delimiters and leading * prefixes per line
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


def _is_static(node: Node) -> bool:
    for child in node.children:
        if child.type == "static":
            return True
    return False


def _is_async(node: Node) -> bool:
    for child in node.children:
        if child.type == "async":
            return True
    return False


class JavaScriptParser(BaseParser):
    """Parses JavaScript source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(JS_LANGUAGE)

    @property
    def language(self) -> str:
        return "javascript"

    @property
    def supported_extensions(self) -> list[str]:
        return [".js", ".mjs", ".cjs"]

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
            language="javascript",
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
                case "import_statement":
                    self._handle_import(child, source, file_path, symbols, relationships)
                case "class_declaration" | "class":
                    self._handle_class(child, source, file_path, symbols, relationships)
                case "function_declaration":
                    self._handle_function(child, source, file_path, symbols, relationships, owner)
                case "lexical_declaration" | "variable_declaration":
                    self._handle_variable(child, source, file_path, symbols, relationships, owner)
                case "export_statement":
                    self._handle_export(child, source, file_path, symbols, relationships, owner)

    def _handle_import(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        source_node = node.child_by_field_name("source")
        if source_node is None:
            return
        module = _node_text(source_node, source).strip("'\"")

        symbols.append(
            Symbol(
                id=_build_id(file_path, f"import.{module}"),
                name=module,
                qualified_name=f"import.{module}",
                kind=SymbolKind.IMPORT,
                file_path=file_path,
                span=_node_span(node),
                language="javascript",
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
        docstring = _get_jsdoc(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="javascript",
            )
        )

        # Inheritance
        heritage = node.child_by_field_name("heritage")
        if heritage:
            for spec in heritage.named_children:
                if spec.type in ("extends_clause", "class_heritage"):
                    parent_text = _node_text(spec, source).removeprefix("extends").strip()
                    if parent_text:
                        relationships.append(
                            Relationship(
                                source_id=_build_id(file_path, name),
                                target_id=f"<unresolved>::{parent_text}",
                                kind=RelationshipKind.INHERITS,
                                file_path=file_path,
                                span=_node_span(node),
                            )
                        )

        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                if member.type == "method_definition":
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
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{owner}.{name}"
        docstring = _get_jsdoc(node, source)

        is_static_method = _is_static(node)
        is_async_method = _is_async(node)
        params = node.child_by_field_name("parameters")
        async_prefix = "async " if is_async_method else ""
        static_prefix = "static " if is_static_method else ""
        sig = f"{static_prefix}{async_prefix}{name}"
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
                docstring=docstring,
                language="javascript",
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
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)
        qualified_name = f"{owner}.{name}" if owner else name
        docstring = _get_jsdoc(node, source)

        is_async_fn = _is_async(node)
        params = node.child_by_field_name("parameters")
        async_prefix = "async " if is_async_fn else ""
        sig = f"{async_prefix}function {name}"
        if params:
            sig += _node_text(params, source)

        kind = SymbolKind.METHOD if owner else SymbolKind.FUNCTION

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
                language="javascript",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, relationships)

    def _handle_variable(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str | None = None,
    ) -> None:
        for decl in node.named_children:
            if decl.type != "variable_declarator":
                continue
            name_node = decl.child_by_field_name("name")
            value_node = decl.child_by_field_name("value")
            if name_node is None:
                continue
            name = _node_text(name_node, source)
            qualified_name = f"{owner}.{name}" if owner else name

            if value_node and value_node.type in ("arrow_function", "function_expression"):
                # Treat as a function
                params = value_node.child_by_field_name(
                    "parameters"
                ) or value_node.child_by_field_name("parameter")
                sig = f"const {name} = "
                if value_node.type == "arrow_function":
                    params_text = _node_text(params, source) if params else "()"
                    sig += f"{params_text} =>"
                else:
                    params_text = _node_text(params, source) if params else "()"
                    sig += f"function{params_text}"

                symbols.append(
                    Symbol(
                        id=_build_id(file_path, qualified_name),
                        name=name,
                        qualified_name=qualified_name,
                        kind=SymbolKind.FUNCTION,
                        file_path=file_path,
                        span=_node_span(decl),
                        signature=sig,
                        language="javascript",
                    )
                )
                body = value_node.child_by_field_name("body")
                if body:
                    self._extract_calls(body, source, file_path, qualified_name, relationships)
            else:
                # Treat as a constant/variable
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, qualified_name),
                        name=name,
                        qualified_name=qualified_name,
                        kind=SymbolKind.CONSTANT,
                        file_path=file_path,
                        span=_node_span(decl),
                        language="javascript",
                    )
                )

    def _handle_export(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        owner: str | None = None,
    ) -> None:
        """Unwrap export statements and parse the inner declaration."""
        for child in node.named_children:
            match child.type:
                case "class_declaration" | "class":
                    self._handle_class(child, source, file_path, symbols, relationships)
                case "function_declaration":
                    self._handle_function(child, source, file_path, symbols, relationships, owner)
                case "lexical_declaration" | "variable_declaration":
                    self._handle_variable(child, source, file_path, symbols, relationships, owner)

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_qualified: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call_expression":
            fn_node = node.child_by_field_name("function")
            if fn_node:
                callee = _node_text(fn_node, source)
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
