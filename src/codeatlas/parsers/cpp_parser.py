"""C++ AST parser using tree-sitter."""

import hashlib
from pathlib import Path

import tree_sitter_cpp as tscpp
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

CPP_LANGUAGE = Language(tscpp.language())


def _node_span(node: Node) -> Span:
    return Span(
        start=Position(line=node.start_point[0], column=node.start_point[1]),
        end=Position(line=node.end_point[0], column=node.end_point[1]),
    )


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _build_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}::{qualified_name}"


def _get_doc_comment(node: Node, source: bytes) -> str | None:
    """Extract preceding /// or /** */ doc comments."""
    prev = node.prev_sibling
    if prev is None:
        return None

    if prev.type == "comment":
        text = _node_text(prev, source).strip()
        # Doxygen-style /** ... */
        if text.startswith("/**") and text.endswith("*/"):
            inner = text[3:-2].strip()
            lines = [ln.lstrip(" *").strip() for ln in inner.split("\n")]
            return "\n".join(ln for ln in lines if ln) or None
        # Triple-slash /// comments (collect consecutive)
        if text.startswith("///"):
            lines: list[str] = []
            cur = prev
            while cur and cur.type == "comment":
                t = _node_text(cur, source).strip()
                if t.startswith("///"):
                    lines.insert(0, t[3:].strip())
                    cur = cur.prev_sibling
                else:
                    break
            return "\n".join(lines) if lines else None
    return None


def _get_base_classes(node: Node, source: bytes) -> list[str]:
    """Extract base class names from a base_class_clause."""
    bases: list[str] = []
    clause = None
    for child in node.children:
        if child.type == "base_class_clause":
            clause = child
            break
    if clause is None:
        return bases
    for child in clause.named_children:
        if child.type in ("type_identifier", "qualified_identifier"):
            bases.append(_node_text(child, source))
    return bases


def _get_declarator_name(node: Node, source: bytes) -> str | None:
    """Extract the function/field name from a declarator chain."""
    decl = node.child_by_field_name("declarator")
    if decl is None:
        return None
    # Walk nested declarators (e.g. pointer_declarator -> function_declarator -> identifier)
    while decl.type in ("pointer_declarator", "reference_declarator", "init_declarator"):
        inner = decl.child_by_field_name("declarator")
        if inner is None:
            break
        decl = inner
    if decl.type == "function_declarator":
        name_node = decl.child_by_field_name("declarator")
        if name_node and name_node.type in ("identifier", "field_identifier"):
            return _node_text(name_node, source)
        if name_node and name_node.type == "destructor_name":
            ident = name_node.child_by_field_name("name")
            if ident is None:
                for c in name_node.named_children:
                    if c.type == "identifier":
                        ident = c
                        break
            return f"~{_node_text(ident, source)}" if ident else None
    if decl.type in ("identifier", "field_identifier"):
        return _node_text(decl, source)
    return None


def _has_function_declarator(node: Node) -> bool:
    """Check if a field_declaration contains a function declarator."""
    decl = node.child_by_field_name("declarator")
    if decl is None:
        return False
    while decl.type in ("pointer_declarator", "reference_declarator"):
        inner = decl.child_by_field_name("declarator")
        if inner is None:
            break
        decl = inner
    return decl.type == "function_declarator"


def _build_func_signature(node: Node, source: bytes, name: str) -> str:
    """Build a function signature from a function_declarator."""
    decl = node.child_by_field_name("declarator")
    if decl is None:
        return name

    # Walk to the function_declarator
    while decl.type in ("pointer_declarator", "reference_declarator", "init_declarator"):
        inner = decl.child_by_field_name("declarator")
        if inner is None:
            break
        decl = inner

    if decl.type != "function_declarator":
        return name

    params = decl.child_by_field_name("parameters")
    # Get return type
    type_node = node.child_by_field_name("type")
    ret = _node_text(type_node, source) if type_node else ""

    sig = f"{ret} {name}" if ret else name
    if params:
        sig += _node_text(params, source)
    # Check for const qualifier
    for child in decl.children:
        if child.type == "type_qualifier" and _node_text(child, source) == "const":
            sig += " const"
    return sig


class CppParser(BaseParser):
    """Parses C++ source files using tree-sitter."""

    def __init__(self) -> None:
        self._parser = Parser(CPP_LANGUAGE)

    @property
    def language(self) -> str:
        return "cpp"

    @property
    def supported_extensions(self) -> list[str]:
        return [".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h"]

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
            language="cpp",
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
                case "preproc_include":
                    self._handle_include(child, source, file_path, symbols, relationships)
                case "namespace_definition":
                    self._handle_namespace(
                        child, source, file_path, symbols, relationships, namespace
                    )
                case "class_specifier":
                    self._handle_class(child, source, file_path, symbols, relationships, namespace)
                case "struct_specifier":
                    self._handle_struct(child, source, file_path, symbols, relationships, namespace)
                case "enum_specifier":
                    self._handle_enum(child, source, file_path, symbols, namespace)
                case "function_definition":
                    self._handle_function_def(
                        child, source, file_path, symbols, relationships, namespace
                    )
                case "declaration":
                    self._handle_declaration(
                        child, source, file_path, symbols, relationships, namespace
                    )
                case "template_declaration":
                    self._handle_template(
                        child, source, file_path, symbols, relationships, namespace
                    )
                case "alias_declaration":
                    self._handle_alias(child, source, file_path, symbols, namespace)

    def _qualify(self, name: str, namespace: str | None) -> str:
        return f"{namespace}::{name}" if namespace else name

    def _handle_include(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
    ) -> None:
        path_node = node.child_by_field_name("path")
        if path_node is None:
            # Try named children for system_lib_string or string_literal
            for child in node.named_children:
                if child.type in ("system_lib_string", "string_literal", "string_content"):
                    path_node = child
                    break
        if path_node is None:
            return

        include_path = _node_text(path_node, source).strip('"<>')
        symbols.append(
            Symbol(
                id=_build_id(file_path, f"include.{include_path}"),
                name=include_path,
                qualified_name=f"include.{include_path}",
                kind=SymbolKind.IMPORT,
                file_path=file_path,
                span=_node_span(node),
                language="cpp",
            )
        )
        relationships.append(
            Relationship(
                source_id=_build_id(file_path, "module"),
                target_id=f"<external>::{include_path}",
                kind=RelationshipKind.IMPORTS,
                file_path=file_path,
                span=_node_span(node),
            )
        )

    def _handle_namespace(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        parent_ns: str | None,
    ) -> None:
        name_node = None
        for child in node.children:
            if child.type == "namespace_identifier":
                name_node = child
                break
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
                language="cpp",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._walk_children(
                body, source, file_path, symbols, relationships, namespace=qualified
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
        docstring = _get_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="cpp",
            )
        )

        # Base classes
        for base in _get_base_classes(node, source):
            relationships.append(
                Relationship(
                    source_id=_build_id(file_path, qualified),
                    target_id=f"<unresolved>::{base}",
                    kind=RelationshipKind.INHERITS,
                    file_path=file_path,
                    span=_node_span(node),
                )
            )

        # Members
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
        docstring = _get_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="cpp",
            )
        )

        for base in _get_base_classes(node, source):
            relationships.append(
                Relationship(
                    source_id=_build_id(file_path, qualified),
                    target_id=f"<unresolved>::{base}",
                    kind=RelationshipKind.INHERITS,
                    file_path=file_path,
                    span=_node_span(node),
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
        docstring = _get_doc_comment(node, source)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=SymbolKind.ENUM,
                file_path=file_path,
                span=_node_span(node),
                docstring=docstring,
                language="cpp",
            )
        )

    def _handle_function_def(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        namespace: str | None,
        owner: str | None = None,
    ) -> None:
        name = _get_declarator_name(node, source)
        if name is None:
            return

        if owner:
            qualified = f"{owner}.{name}"
            kind = SymbolKind.METHOD
        else:
            qualified = self._qualify(name, namespace)
            kind = SymbolKind.FUNCTION

        docstring = _get_doc_comment(node, source)
        signature = _build_func_signature(node, source, name)

        symbols.append(
            Symbol(
                id=_build_id(file_path, qualified),
                name=name,
                qualified_name=qualified,
                kind=kind,
                file_path=file_path,
                span=_node_span(node),
                signature=signature,
                docstring=docstring,
                language="cpp",
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, source, file_path, qualified, relationships)

    def _handle_declaration(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        namespace: str | None,
    ) -> None:
        """Handle top-level declarations (free function declarations, constants)."""
        name = _get_declarator_name(node, source)
        if name is None:
            return

        if _has_function_declarator(node):
            # Function declaration (prototype)
            qualified = self._qualify(name, namespace)
            signature = _build_func_signature(node, source, name)
            symbols.append(
                Symbol(
                    id=_build_id(file_path, qualified),
                    name=name,
                    qualified_name=qualified,
                    kind=SymbolKind.FUNCTION,
                    file_path=file_path,
                    span=_node_span(node),
                    signature=signature,
                    language="cpp",
                )
            )
        else:
            # Variable or constant declaration
            is_const = any(
                c.type == "type_qualifier" and _node_text(c, source) == "const"
                for c in node.children
            )
            qualified = self._qualify(name, namespace)
            symbols.append(
                Symbol(
                    id=_build_id(file_path, qualified),
                    name=name,
                    qualified_name=qualified,
                    kind=SymbolKind.CONSTANT if is_const else SymbolKind.VARIABLE,
                    file_path=file_path,
                    span=_node_span(node),
                    language="cpp",
                )
            )

    def _handle_template(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        namespace: str | None,
    ) -> None:
        """Handle template declarations — delegate to the inner declaration."""
        for child in node.named_children:
            if child.type == "class_specifier":
                self._handle_class(child, source, file_path, symbols, relationships, namespace)
            elif child.type == "struct_specifier":
                self._handle_struct(child, source, file_path, symbols, relationships, namespace)
            elif child.type == "function_definition":
                self._handle_function_def(
                    child, source, file_path, symbols, relationships, namespace
                )
            elif child.type == "declaration":
                self._handle_declaration(
                    child, source, file_path, symbols, relationships, namespace
                )

    def _handle_alias(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        symbols: list[Symbol],
        namespace: str | None,
    ) -> None:
        """Handle 'using X = ...' type alias declarations."""
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
                kind=SymbolKind.TYPE_ALIAS,
                file_path=file_path,
                span=_node_span(node),
                language="cpp",
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
        """Extract methods and fields from a class/struct body."""
        for child in body.named_children:
            if child.type == "function_definition":
                self._handle_function_def(
                    child,
                    source,
                    file_path,
                    symbols,
                    relationships,
                    namespace=None,
                    owner=owner,
                )
            elif child.type == "field_declaration":
                if _has_function_declarator(child):
                    # Method declaration (no body)
                    name = _get_declarator_name(child, source)
                    if name is None:
                        continue
                    qualified = f"{owner}.{name}"
                    signature = _build_func_signature(child, source, name)
                    docstring = _get_doc_comment(child, source)
                    symbols.append(
                        Symbol(
                            id=_build_id(file_path, qualified),
                            name=name,
                            qualified_name=qualified,
                            kind=SymbolKind.METHOD,
                            file_path=file_path,
                            span=_node_span(child),
                            signature=signature,
                            docstring=docstring,
                            language="cpp",
                        )
                    )
                else:
                    # Field
                    name = _get_declarator_name(child, source)
                    if name is None:
                        continue
                    qualified = f"{owner}.{name}"
                    symbols.append(
                        Symbol(
                            id=_build_id(file_path, qualified),
                            name=name,
                            qualified_name=qualified,
                            kind=SymbolKind.VARIABLE,
                            file_path=file_path,
                            span=_node_span(child),
                            language="cpp",
                        )
                    )
            elif child.type == "declaration":
                # Constructor / destructor declarations
                name = _get_declarator_name(child, source)
                if name is None:
                    continue
                qualified = f"{owner}.{name}"
                signature = _build_func_signature(child, source, name)
                symbols.append(
                    Symbol(
                        id=_build_id(file_path, qualified),
                        name=name,
                        qualified_name=qualified,
                        kind=SymbolKind.METHOD,
                        file_path=file_path,
                        span=_node_span(child),
                        signature=signature,
                        language="cpp",
                    )
                )

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
                # For field_expression calls like obj.method, extract method name
                if func_node.type == "field_expression":
                    field = func_node.child_by_field_name("field")
                    obj = func_node.child_by_field_name("argument")
                    if field and obj:
                        callee = f"{_node_text(obj, source)}.{_node_text(field, source)}"
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
