"""Parser registry - routes files to the correct language parser."""

from pathlib import Path

from codeatlas.models import ParseResult
from codeatlas.parsers.base import BaseParser
from codeatlas.parsers.bash_parser import BashParser
from codeatlas.parsers.c_parser import CParser
from codeatlas.parsers.cpp_parser import CppParser
from codeatlas.parsers.csharp_parser import CSharpParser
from codeatlas.parsers.elixir_parser import ElixirParser
from codeatlas.parsers.go_parser import GoParser
from codeatlas.parsers.haskell_parser import HaskellParser
from codeatlas.parsers.java_parser import JavaParser
from codeatlas.parsers.javascript_parser import JavaScriptParser
from codeatlas.parsers.julia_parser import JuliaParser
from codeatlas.parsers.kotlin_parser import KotlinParser
from codeatlas.parsers.lua_parser import LuaParser
from codeatlas.parsers.ocaml_parser import OCamlParser
from codeatlas.parsers.php_parser import PhpParser
from codeatlas.parsers.powershell_parser import PowerShellParser
from codeatlas.parsers.python_parser import PythonParser
from codeatlas.parsers.ruby_parser import RubyParser
from codeatlas.parsers.rust_parser import RustParser
from codeatlas.parsers.scala_parser import ScalaParser
from codeatlas.parsers.sql_parser import SqlParser
from codeatlas.parsers.svelte_parser import SvelteParser
from codeatlas.parsers.swift_parser import SwiftParser
from codeatlas.parsers.typescript_parser import TypeScriptParser
from codeatlas.parsers.zig_parser import ZigParser


class ParserRegistry:
    """Routes files to the correct parser by extension."""

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}
        for parser in [
            PythonParser(),
            TypeScriptParser(),
            GoParser(),
            RustParser(),
            JavaParser(),
            CppParser(),
            CSharpParser(),
            RubyParser(),
            JavaScriptParser(),
            KotlinParser(),
            PhpParser(),
            ScalaParser(),
            CParser(),
            ZigParser(),
            OCamlParser(),
            BashParser(),
            LuaParser(),
            ElixirParser(),
            SwiftParser(),
            HaskellParser(),
            SqlParser(),
            JuliaParser(),
            PowerShellParser(),
            SvelteParser(),
        ]:
            for ext in parser.supported_extensions:
                self._parsers[ext] = parser

    def get_parser(self, path: Path) -> BaseParser | None:
        return self._parsers.get(path.suffix.lower())

    def parse_file(self, path: Path) -> ParseResult | None:
        parser = self.get_parser(path)
        if parser is None:
            return None
        return parser.parse_file(path)

    @property
    def supported_extensions(self) -> list[str]:
        return list(self._parsers.keys())
