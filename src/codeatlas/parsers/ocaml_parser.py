"""Tree-sitter parser for OCaml source files (.ml, .mli)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_ocaml as tsocaml
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

_OCAML_LANGUAGE = Language(tsocaml.language_ocaml())

# OCaml standard library functions to skip as call targets
_OCAML_STDLIB = frozenset(
    {
        "print_string",
        "print_int",
        "print_float",
        "print_endline",
        "print_newline",
        "Printf",
        "printf",
        "sprintf",
        "failwith",
        "invalid_arg",
        "raise",
        "ignore",
        "fst",
        "snd",
        "not",
        "succ",
        "pred",
        "abs",
        "max",
        "min",
    }
)


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _build_id(file_path: str, name: str) -> str:
    return f"{file_path}::{name}"


class OCamlParser(BaseParser):
    """Parser for OCaml source files using tree-sitter.

    Extracts:
    - open Module → IMPORT
    - let name [params] = ... → FUNCTION
    - type name = variant | record | alias → CLASS
    - module Name = struct ... end → MODULE
    - call/application expressions → CALLS
    """

    def __init__(self) -> None:
        self._parser = Parser(_OCAML_LANGUAGE)

    @property
    def language(self) -> str:
        return "ocaml"

    @property
    def supported_extensions(self) -> list[str]:
        return [".ml", ".mli"]

    def parse_file(self, path: Path) -> ParseResult:
        source = path.read_bytes()
        return self._parse(source, str(path))

    def parse_source(self, source: str, file_path: str) -> ParseResult:
        return self._parse(source.encode("utf-8"), file_path)

    def _parse(self, source: bytes, file_path: str) -> ParseResult:
        tree = self._parser.parse(source)
        symbols: list[Symbol] = []
        relationships: list[Relationship] = []
        for node in tree.root_node.named_children:
            self._visit(node, source, file_path, symbols, relationships)
        fi = FileInfo(
            path=file_path,
            language=self.language,
            content_hash=hashlib.sha256(source).hexdigest(),
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=fi, symbols=symbols, relationships=relationships)

    def _visit(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        if node.type == "open_module":
            self._handle_open(node, source, file_path, symbols)
        elif node.type == "value_definition":
            self._handle_value(node, source, file_path, symbols, relationships)
        elif node.type == "type_definition":
            self._handle_type(node, source, file_path, symbols)
        elif node.type == "module_definition":
            self._handle_module(node, source, file_path, symbols, relationships)

    def _handle_open(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        mod_path = next((c for c in node.named_children if c.type == "module_path"), None)
        if mod_path is None:
            return
        mod_name_node = next((c for c in mod_path.named_children if c.type == "module_name"), None)
        if mod_name_node is None:
            return
        name = _text(mod_name_node, source)
        symbols.append(
            Symbol(
                id=_build_id(file_path, f"open.{name}"),
                name=name,
                qualified_name=f"open.{name}",
                kind=SymbolKind.IMPORT,
                file_path=file_path,
                span=_span(node),
                language="ocaml",
            )
        )

    def _handle_value(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        binding = next((c for c in node.named_children if c.type == "let_binding"), None)
        if binding is None:
            return
        name_node = next((c for c in binding.named_children if c.type == "value_name"), None)
        if name_node is None:
            return
        name = _text(name_node, source)

        # Has parameters → function, else → constant/value
        params = [c for c in binding.named_children if c.type == "parameter"]
        if params:
            param_texts = [_text(p, source).strip() for p in params]
            signature = f"let {name} {' '.join(param_texts)}"
            kind = SymbolKind.FUNCTION
        else:
            signature = f"let {name}"
            kind = SymbolKind.FUNCTION  # OCaml values are first-class

        sym = Symbol(
            id=_build_id(file_path, name),
            name=name,
            qualified_name=name,
            kind=kind,
            file_path=file_path,
            span=_span(node),
            signature=signature,
            language="ocaml",
        )
        symbols.append(sym)

        # Collect calls in the binding body
        body = next(
            (
                c
                for c in binding.named_children
                if c.type not in ("value_name", "parameter", "type_constructor", "type_annotation")
            ),
            None,
        )
        if body:
            self._collect_calls(body, source, file_path, sym.id, relationships)

    def _handle_type(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        for binding in node.named_children:
            if binding.type != "type_binding":
                continue
            type_ctor = next(
                (c for c in binding.named_children if c.type == "type_constructor"), None
            )
            if type_ctor is None:
                continue
            name = _text(type_ctor, source)
            symbols.append(
                Symbol(
                    id=_build_id(file_path, name),
                    name=name,
                    qualified_name=name,
                    kind=SymbolKind.CLASS,
                    file_path=file_path,
                    span=_span(binding),
                    language="ocaml",
                )
            )

    def _handle_module(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        binding = next((c for c in node.named_children if c.type == "module_binding"), None)
        if binding is None:
            return
        name_node = next((c for c in binding.named_children if c.type == "module_name"), None)
        if name_node is None:
            return
        name = _text(name_node, source)
        sym = Symbol(
            id=_build_id(file_path, name),
            name=name,
            qualified_name=name,
            kind=SymbolKind.MODULE,
            file_path=file_path,
            span=_span(node),
            language="ocaml",
        )
        symbols.append(sym)

        # Extract nested value definitions inside the struct
        structure = next((c for c in binding.named_children if c.type == "structure"), None)
        if structure:
            for child in structure.named_children:
                if child.type == "value_definition":
                    self._handle_nested_value(
                        child, source, file_path, name, symbols, relationships
                    )

    def _handle_nested_value(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        module_name: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        binding = next((c for c in node.named_children if c.type == "let_binding"), None)
        if binding is None:
            return
        name_node = next((c for c in binding.named_children if c.type == "value_name"), None)
        if name_node is None:
            return
        short_name = _text(name_node, source)
        qualified = f"{module_name}.{short_name}"

        params = [c for c in binding.named_children if c.type == "parameter"]
        signature = f"let {qualified} {' '.join(_text(p, source).strip() for p in params)}".strip()

        sym = Symbol(
            id=_build_id(file_path, qualified),
            name=short_name,
            qualified_name=qualified,
            kind=SymbolKind.METHOD,
            file_path=file_path,
            span=_span(node),
            signature=signature,
            language="ocaml",
        )
        symbols.append(sym)

        body = next(
            (c for c in binding.named_children if c.type not in ("value_name", "parameter")),
            None,
        )
        if body:
            self._collect_calls(body, source, file_path, sym.id, relationships)

    def _collect_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_id: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "application_expression":
            # First child is the function being called
            func_node = next((c for c in node.named_children if c.type == "value_path"), None)
            if func_node:
                name_node = next(
                    (c for c in func_node.named_children if c.type == "value_name"), None
                )
                if name_node:
                    name = _text(name_node, source)
                    if name not in _OCAML_STDLIB:
                        relationships.append(
                            Relationship(
                                source_id=caller_id,
                                target_id=_build_id(file_path, name),
                                kind=RelationshipKind.CALLS,
                                file_path=file_path,
                                span=_span(node),
                            )
                        )
                else:
                    # Direct value_path without value_name child
                    name = _text(func_node, source)
                    if name not in _OCAML_STDLIB:
                        relationships.append(
                            Relationship(
                                source_id=caller_id,
                                target_id=_build_id(file_path, name),
                                kind=RelationshipKind.CALLS,
                                file_path=file_path,
                                span=_span(node),
                            )
                        )
        for child in node.named_children:
            self._collect_calls(child, source, file_path, caller_id, relationships)
