"""Tree-sitter parser for C source files (.c, .h)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_c as tsc
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

_C_LANGUAGE = Language(tsc.language())

# C standard library functions to skip as call targets
_C_STDLIB = frozenset(
    {
        "printf",
        "fprintf",
        "sprintf",
        "snprintf",
        "scanf",
        "malloc",
        "calloc",
        "realloc",
        "free",
        "memcpy",
        "memmove",
        "memset",
        "strlen",
        "strcpy",
        "strncpy",
        "strcmp",
        "strncmp",
        "strcat",
        "strncat",
        "fopen",
        "fclose",
        "fread",
        "fwrite",
        "fgets",
        "exit",
        "abort",
        "assert",
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


class CParser(BaseParser):
    """Parser for C source files using tree-sitter.

    Extracts:
    - #include directives → IMPORT
    - function definitions → FUNCTION
    - typedef struct / struct → CLASS
    - typedef enum / enum → CLASS
    - typedef function pointers → TYPE_ALIAS
    - call expressions → CALLS
    """

    def __init__(self) -> None:
        self._parser = Parser(_C_LANGUAGE)

    @property
    def language(self) -> str:
        return "c"

    @property
    def supported_extensions(self) -> list[str]:
        return [".c"]

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
        if node.type == "preproc_include":
            self._handle_include(node, source, file_path, symbols, relationships)
        elif node.type == "function_definition":
            self._handle_function(node, source, file_path, symbols, relationships)
        elif node.type == "type_definition":
            self._handle_typedef(node, source, file_path, symbols)
        elif node.type in ("struct_specifier", "enum_specifier"):
            # Top-level anonymous struct/enum with a tag
            self._handle_tagged_type(node, source, file_path, symbols)

    def _handle_include(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        # system_lib_string → <stdio.h>, string_literal → "local.h"
        path_node = next(
            (c for c in node.named_children if c.type in ("system_lib_string", "string_literal")),
            None,
        )
        if path_node is None:
            return
        raw = _text(path_node, source).strip("<>\"'")
        name = raw
        sym = Symbol(
            id=_build_id(file_path, f"include.{name}"),
            name=name,
            qualified_name=f"include.{name}",
            kind=SymbolKind.IMPORT,
            file_path=file_path,
            span=_span(node),
            language="c",
        )
        symbols.append(sym)
        relationships.append(
            Relationship(
                source_id=_build_id(file_path, "module"),
                target_id=f"<external>::{name}",
                kind=RelationshipKind.IMPORTS,
                file_path=file_path,
                span=_span(node),
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
        declarator = next((c for c in node.named_children if c.type == "function_declarator"), None)
        if declarator is None:
            return
        name_node = next((c for c in declarator.named_children if c.type == "identifier"), None)
        if name_node is None:
            return
        name = _text(name_node, source)

        # Build parameter signature
        param_list = next(
            (c for c in declarator.named_children if c.type == "parameter_list"), None
        )
        params_text = _text(param_list, source) if param_list else "()"

        # Return type: everything before the declarator
        ret_parts = []
        for child in node.named_children:
            if child == declarator:
                break
            ret_parts.append(_text(child, source).strip())
        ret_type = " ".join(p for p in ret_parts if p)
        signature = f"{ret_type} {name}{params_text}".strip()

        sym = Symbol(
            id=_build_id(file_path, name),
            name=name,
            qualified_name=name,
            kind=SymbolKind.FUNCTION,
            file_path=file_path,
            span=_span(node),
            signature=signature,
            language="c",
        )
        symbols.append(sym)

        # Collect calls inside function body
        body = next((c for c in node.named_children if c.type == "compound_statement"), None)
        if body:
            self._collect_calls(body, source, file_path, sym.id, relationships)

    def _handle_typedef(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        # typedef struct { ... } Name  OR  typedef int Name  OR  typedef int (*FnPtr)(...)
        # Direct type_identifier child (struct/enum typedefs end with the alias name)
        type_name = next((c for c in node.named_children if c.type == "type_identifier"), None)
        if type_name is None:
            # Function pointer typedef: name is nested inside function_declarator
            type_name = self._find_type_identifier(node)
        if type_name is None:
            return
        name = _text(type_name, source)

        inner = next(
            (
                c
                for c in node.named_children
                if c.type in ("struct_specifier", "enum_specifier", "union_specifier")
            ),
            None,
        )
        if inner is not None:
            kind = SymbolKind.CLASS
        else:
            # function pointer typedef or simple alias
            kind = SymbolKind.TYPE_ALIAS

        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=kind,
                file_path=file_path,
                span=_span(node),
                language="c",
            )
        )

    def _handle_tagged_type(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        tag = next((c for c in node.named_children if c.type == "type_identifier"), None)
        if tag is None:
            return
        name = _text(tag, source)
        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_span(node),
                language="c",
            )
        )

    def _find_type_identifier(self, node: Node) -> Node | None:
        """Recursively search for a type_identifier node (used for function pointer typedefs)."""
        for child in node.named_children:
            if child.type == "type_identifier":
                return child
            result = self._find_type_identifier(child)
            if result is not None:
                return result
        return None

    def _collect_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_id: str,
        relationships: list[Relationship],
    ) -> None:
        if node.type == "call_expression":
            callee = next((c for c in node.named_children if c.type == "identifier"), None)
            if callee:
                name = _text(callee, source)
                if name not in _C_STDLIB:
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
