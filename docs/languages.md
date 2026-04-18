# Supported languages

CodeAtlas ships 26 tree-sitter parsers out of the box. Run `codeatlas languages` for the live list.

| Language | File extensions | Symbols extracted |
|---|---|---|
| Python | `.py` | classes, functions, methods, decorators, imports, variables |
| TypeScript | `.ts`, `.tsx` | classes, interfaces, types, functions, methods, enums |
| JavaScript | `.js`, `.mjs`, `.cjs`, `.jsx` | classes, functions, methods, exports |
| Go | `.go` | structs, interfaces, functions, methods |
| Rust | `.rs` | structs, enums, traits, impls, functions, modules |
| Java | `.java` | classes, interfaces, methods, fields |
| Kotlin | `.kt`, `.kts` | classes, objects, functions, properties |
| C | `.c`, `.h` | functions, structs, typedefs, macros |
| C++ | `.cpp`, `.hpp`, `.cc`, `.cxx` | classes, structs, namespaces, templates |
| C# | `.cs` | classes, structs, interfaces, methods, properties |
| Ruby | `.rb` | classes, modules, methods |
| PHP | `.php` | classes, interfaces, traits, functions |
| Scala | `.scala`, `.sc` | classes, objects, traits, defs |
| Swift | `.swift` | classes, structs, protocols, enums, functions |
| Haskell | `.hs` | data, newtype, class, functions with type sigs |
| Bash | `.sh`, `.bash`, `.zsh` | functions |
| Lua | `.lua` | functions, tables |
| Elixir | `.ex`, `.exs` | modules, functions |
| SQL | `.sql` | tables, views, procedures, functions |
| Zig | `.zig` | functions, structs, enums, imports |
| OCaml | `.ml`, `.mli` | modules, types, functions |
| Julia | `.jl` | modules, functions, structs |
| PowerShell | `.ps1`, `.psm1` | functions, cmdlets |
| Svelte | `.svelte` | components, script blocks |

## Adding a new language

1. Add the grammar wheel to `[project.dependencies]` in `pyproject.toml`.
2. Create `src/codeatlas/parsers/<lang>_parser.py` that subclasses `LanguageParser`.
3. Register the extension list in `src/codeatlas/parsers/__init__.py`.
4. Add fixtures under `tests/fixtures/sample_<lang>/` and a test module under `tests/test_parsers/`.

The base class handles file I/O, span calculation, UTF-8 offsets, and test-file detection — parsers only need to walk the tree-sitter AST.
