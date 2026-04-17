"""Svelte component parser using tree-sitter.

Parses Svelte (.svelte) files by:
1. Using tree-sitter-svelte to locate <script> blocks
2. Re-parsing the script content with tree-sitter-javascript
3. Emitting a top-level COMPONENT symbol for the file itself
"""

import hashlib
from pathlib import Path

import tree_sitter_javascript as tsjs
import tree_sitter_svelte as tssvelte
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

SVELTE_LANGUAGE = Language(tssvelte.language())
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


def _js_node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_jsdoc(node: Node, source: bytes) -> str | None:
    """Extract preceding // or /** */ comment."""
    prev = node.prev_sibling
    while prev and prev.type in ("comment", "block_comment"):
        text = _js_node_text(prev, source).strip()
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


class SvelteParser(BaseParser):
    """Parses Svelte component files using tree-sitter."""

    def __init__(self) -> None:
        self._svelte_parser = Parser(SVELTE_LANGUAGE)
        self._js_parser = Parser(JS_LANGUAGE)

    @property
    def language(self) -> str:
        return "svelte"

    @property
    def supported_extensions(self) -> list[str]:
        return [".svelte"]

    def parse_file(self, path: Path) -> ParseResult:
        source = path.read_bytes()
        return self._parse(source, str(path))

    def parse_source(self, source: str, file_path: str) -> ParseResult:
        return self._parse(source.encode("utf-8"), file_path)

    def _parse(self, source: bytes, file_path: str) -> ParseResult:
        content_hash = hashlib.sha256(source).hexdigest()
        tree = self._svelte_parser.parse(source)
        root = tree.root_node

        symbols: list[Symbol] = []
        relationships: list[Relationship] = []

        # The component itself is a top-level symbol
        component_name = Path(file_path).stem
        component_id = _build_id(file_path, component_name)
        symbols.append(
            Symbol(
                id=component_id,
                name=component_name,
                qualified_name=component_name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(root),
                language="svelte",
            )
        )

        # Find <script> blocks and parse their content as JavaScript
        for child in root.named_children:
            if child.type == "script_element":
                self._handle_script(
                    child, source, file_path, component_name, symbols, relationships
                )

        file_info = FileInfo(
            path=file_path,
            language="svelte",
            content_hash=content_hash,
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=file_info, symbols=symbols, relationships=relationships)

    def _handle_script(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        component_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Find raw_text child which contains the script content
        raw_text_node = None
        for child in node.named_children:
            if child.type == "raw_text":
                raw_text_node = child
                break
        if raw_text_node is None:
            return

        # The raw_text is a slice of the original source
        script_bytes = source[raw_text_node.start_byte : raw_text_node.end_byte]
        # The script starts at this line offset in the file
        line_offset = raw_text_node.start_point[0]

        # Parse the JS content
        js_tree = self._js_parser.parse(script_bytes)
        js_root = js_tree.root_node

        self._walk_js(
            js_root,
            script_bytes,
            file_path,
            component_name,
            line_offset,
            symbols,
            relationships,
        )

    def _walk_js(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        owner: str,
        line_offset: int,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        for child in node.named_children:
            match child.type:
                case "import_statement":
                    self._handle_import(
                        child, source, file_path, owner, line_offset, symbols, relationships
                    )
                case "function_declaration":
                    self._handle_function(
                        child, source, file_path, owner, line_offset, symbols, relationships
                    )
                case "lexical_declaration" | "variable_declaration":
                    self._handle_var(
                        child, source, file_path, owner, line_offset, symbols, relationships
                    )
                case _:
                    self._walk_js(
                        child, source, file_path, owner, line_offset, symbols, relationships
                    )

    def _adjusted_span(self, node: Node, line_offset: int) -> Span:
        return Span(
            start=Position(line=node.start_point[0] + line_offset, column=node.start_point[1]),
            end=Position(line=node.end_point[0] + line_offset, column=node.end_point[1]),
        )

    def _handle_import(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        owner: str,
        line_offset: int,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Find string node for the module path
        path_node = None
        for child in node.named_children:
            if child.type == "string":
                path_node = child
                break
        if path_node is None:
            return

        raw = _js_node_text(path_node, source).strip("\"'")
        short = raw.rsplit("/", 1)[-1].replace(".svelte", "").replace(".js", "")
        qualified = f"import.{raw}"

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=short,
                qualified_name=qualified,
                kind=SymbolKind.IMPORT,
                file_path=file_path,
                span=self._adjusted_span(node, line_offset),
                language="svelte",
            )
        )
        relationships.append(
            Relationship(
                source_id=_build_id(file_path, owner),
                target_id=f"<external>::{raw}",
                kind=RelationshipKind.IMPORTS,
                file_path=file_path,
                span=self._adjusted_span(node, line_offset),
            )
        )

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        owner: str,
        line_offset: int,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _js_node_text(name_node, source)
        qualified_name = f"{owner}.{name}"
        docstring = _get_jsdoc(node, source)

        # Check for async
        async_prefix = ""
        for child in node.children:
            if child.type == "async":
                async_prefix = "async "
                break

        params = node.child_by_field_name("parameters")
        sig = f"{async_prefix}function {name}"
        if params:
            sig += _js_node_text(params, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified_name),
                name=name,
                qualified_name=qualified_name,
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                span=self._adjusted_span(node, line_offset),
                signature=sig,
                docstring=docstring,
                language="svelte",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified_name, line_offset, relationships)

    def _handle_var(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        owner: str,
        line_offset: int,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # Check for arrow function declarations: let foo = () => {}
        for decl in node.named_children:
            if decl.type != "variable_declarator":
                continue
            name_node = decl.child_by_field_name("name")
            value_node = decl.child_by_field_name("value")
            if name_node is None or value_node is None:
                continue
            name = _js_node_text(name_node, source)
            if value_node.type == "arrow_function":
                qualified_name = f"{owner}.{name}"
                params = value_node.child_by_field_name(
                    "parameters"
                ) or value_node.child_by_field_name("parameter")
                param_text = _js_node_text(params, source) if params else "()"
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, qualified_name),
                        name=name,
                        qualified_name=qualified_name,
                        kind=SymbolKind.FUNCTION,
                        file_path=file_path,
                        span=self._adjusted_span(node, line_offset),
                        signature=f"const {name} = ({param_text}) => ...",
                        language="svelte",
                    )
                )
                body = value_node.child_by_field_name("body")
                if body:
                    self._extract_calls(
                        body, source, file_path, qualified_name, line_offset, relationships
                    )

    def _extract_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller: str,
        line_offset: int,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call_expression":
            fn_node = node.child_by_field_name("function")
            if fn_node and fn_node.type == "identifier":
                callee = _js_node_text(fn_node, source)
                if callee not in ("console", "fetch", "setTimeout", "setInterval"):
                    relationships.append(
                        Relationship(
                            source_id=_build_id(file_path, caller),
                            target_id=f"<unresolved>::{callee}",
                            kind=RelationshipKind.CALLS,
                            file_path=file_path,
                            span=self._adjusted_span(node, line_offset),
                        )
                    )
        for child in node.children:
            self._extract_calls(child, source, file_path, caller, line_offset, relationships)
