"""Tree-sitter parser for Haskell source files."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_haskell as tshaskell
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

_HASKELL_LANGUAGE = Language(tshaskell.language())

# Haskell Prelude functions to skip as call targets
_PRELUDE = frozenset(
    {
        "putStrLn",
        "putStr",
        "print",
        "getLine",
        "return",
        "pure",
        "fmap",
        "map",
        "filter",
        "foldr",
        "foldl",
        "length",
        "null",
        "head",
        "tail",
        "show",
        "read",
        "error",
        "undefined",
        "otherwise",
        "not",
        "and",
        "or",
        "any",
        "all",
    }
)


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


class HaskellParser(BaseParser):
    """Parser for Haskell source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(_HASKELL_LANGUAGE)

    @property
    def language(self) -> str:
        return "haskell"

    @property
    def supported_extensions(self) -> list[str]:
        return [".hs", ".lhs"]

    def parse_file(self, path: Path) -> ParseResult:
        source = path.read_bytes()
        return self._parse(source, str(path))

    def parse_source(self, source: str, file_path: str) -> ParseResult:
        return self._parse(source.encode("utf-8"), file_path)

    def _parse(self, source: bytes, file_path: str) -> ParseResult:
        tree = self._parser.parse(source)
        root = tree.root_node
        symbols: list[Symbol] = []
        relationships: list[Relationship] = []

        # Module name
        module_name = "Main"
        header = next((c for c in root.named_children if c.type == "header"), None)
        if header:
            mod_node = next((c for c in header.named_children if c.type == "module"), None)
            if mod_node:
                module_name = _node_text(mod_node, source)

        # Collect type signatures: name → type string (for docstring/signature)
        sigs: dict[str, str] = {}
        decls_node = next((c for c in root.named_children if c.type == "declarations"), None)
        if decls_node:
            for child in decls_node.named_children:
                if child.type == "signature":
                    var = next((c for c in child.named_children if c.type == "variable"), None)
                    if var:
                        sigs[_node_text(var, source)] = _node_text(child, source)

        # Imports
        imports_node = next((c for c in root.named_children if c.type == "imports"), None)
        if imports_node:
            for imp in imports_node.named_children:
                if imp.type == "import":
                    mod_child = next((c for c in imp.named_children if c.type == "module"), None)
                    if mod_child:
                        mod_text = _node_text(mod_child, source)
                        sym = Symbol(
                            id=_build_id(file_path, f"import.{mod_text}"),
                            name=mod_text,
                            qualified_name=f"import.{mod_text}",
                            kind=SymbolKind.IMPORT,
                            file_path=file_path,
                            span=_node_span(imp),
                            language="haskell",
                        )
                        symbols.append(sym)
                        relationships.append(
                            Relationship(
                                source_id=_build_id(file_path, module_name),
                                target_id=f"<external>::{mod_text}",
                                kind=RelationshipKind.IMPORTS,
                                file_path=file_path,
                                span=_node_span(imp),
                            )
                        )

        # Declarations
        if decls_node:
            for child in decls_node.named_children:
                self._handle_decl(
                    child, source, file_path, module_name, sigs, symbols, relationships
                )

        fi = FileInfo(
            path=file_path,
            language=self.language,
            content_hash=hashlib.sha256(source).hexdigest(),
            symbol_count=len(symbols),
            relationship_count=len(relationships),
            size_bytes=len(source),
        )
        return ParseResult(file_info=fi, symbols=symbols, relationships=relationships)

    # ------------------------------------------------------------------ #

    def _handle_decl(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        module_name: str,
        sigs: dict[str, str],
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        match node.type:
            case "function" | "bind":
                self._handle_function(
                    node, source, file_path, module_name, sigs, symbols, relationships
                )
            case "data_type":
                self._handle_data_type(node, source, file_path, symbols)
            case "type_synomym":
                self._handle_type_synonym(node, source, file_path, symbols)
            case "newtype":
                self._handle_newtype(node, source, file_path, symbols)
            case "class":
                self._handle_class(node, source, file_path, symbols)
            case _:
                pass  # signature nodes handled via sigs dict above

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        module_name: str,
        sigs: dict[str, str],
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        var_node = next((c for c in node.named_children if c.type == "variable"), None)
        if var_node is None:
            return
        name = _node_text(var_node, source)
        qualified = f"{module_name}.{name}"
        sig = sigs.get(name)

        sym = Symbol(
            id=_build_id(file_path, qualified),
            name=name,
            qualified_name=qualified,
            kind=SymbolKind.FUNCTION,
            file_path=file_path,
            span=_node_span(node),
            signature=sig,
            language="haskell",
        )
        symbols.append(sym)

        # Collect calls from body
        self._collect_calls(node, source, file_path, sym.id, relationships, set())

    def _handle_data_type(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        # data Color = Red | Green | Blue
        name_node = next((c for c in node.named_children if c.type in ("name", "type_name")), None)
        if name_node is None:
            # Fall back: first uppercase identifier in text
            text = _node_text(node, source)
            parts = text.split()
            name = parts[1] if len(parts) > 1 else "Unknown"
        else:
            name = _node_text(name_node, source)
        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                language="haskell",
            )
        )

    def _handle_type_synonym(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        # type Name = String
        text = _node_text(node, source)
        parts = text.split()
        name = parts[1] if len(parts) > 1 else "Unknown"
        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.TYPE_ALIAS,
                file_path=file_path,
                span=_node_span(node),
                language="haskell",
            )
        )

    def _handle_newtype(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        # newtype Wrapper a = Wrapper { unwrap :: a }
        text = _node_text(node, source)
        parts = text.split()
        name = parts[1] if len(parts) > 1 else "Unknown"
        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                language="haskell",
            )
        )

    def _handle_class(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
    ) -> None:
        # class Animal a where ...
        text = _node_text(node, source)
        parts = text.split()
        name = parts[1] if len(parts) > 1 else "Unknown"
        symbols.append(
            Symbol(
                id=_build_id(file_path, name),
                name=name,
                qualified_name=name,
                kind=SymbolKind.INTERFACE,
                file_path=file_path,
                span=_node_span(node),
                language="haskell",
            )
        )

    # ------------------------------------------------------------------ #
    # Call collection                                                      #
    # ------------------------------------------------------------------ #

    def _collect_calls(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        caller_id: str,
        relationships: list[Relationship],
        seen: set[str],
    ) -> None:
        if node.type == "apply":
            # First named child of an apply expression is the callee
            callee = node.named_children[0] if node.named_children else None
            if callee is not None and callee.type == "variable":
                name = _node_text(callee, source)
                if name not in _PRELUDE and name not in seen:
                    seen.add(name)
                    relationships.append(
                        Relationship(
                            source_id=caller_id,
                            target_id=f"<unresolved>::{name}",
                            kind=RelationshipKind.CALLS,
                            file_path=file_path,
                            span=_node_span(node),
                        )
                    )
        for child in node.named_children:
            self._collect_calls(child, source, file_path, caller_id, relationships, seen)
