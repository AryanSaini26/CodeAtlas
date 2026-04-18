"""SQLite-backed code knowledge graph store."""

import re
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from codeatlas.models import FileInfo, ParseResult, Relationship, Symbol

# Regex to identify test files by path patterns
_TEST_FILE_RE = re.compile(
    r"([\\/])(tests?|spec|__tests__)[\\/]"
    r"|[\\/](test_[^/\\]+|[^/\\]+_test|[^/\\]+\.spec|[^/\\]+\.test)\.[a-z]+$",
    re.IGNORECASE,
)


class GraphStore:
    """
    Stores symbols, relationships, and file metadata in a SQLite database.
    Uses WAL mode, FTS5 for keyword search, and recursive CTEs for graph traversals.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self) -> None:
        conn = self._conn
        if self._db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                path        TEXT PRIMARY KEY,
                language    TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                symbol_count INTEGER DEFAULT 0,
                relationship_count INTEGER DEFAULT 0,
                size_bytes  INTEGER DEFAULT 0,
                indexed_at  REAL DEFAULT (unixepoch('now', 'subsec')),
                is_test     INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS symbols (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                qualified_name  TEXT NOT NULL,
                kind            TEXT NOT NULL,
                file_path       TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
                start_line      INTEGER NOT NULL,
                start_col       INTEGER NOT NULL,
                end_line        INTEGER NOT NULL,
                end_col         INTEGER NOT NULL,
                docstring       TEXT,
                signature       TEXT,
                decorators      TEXT,
                language        TEXT NOT NULL DEFAULT 'unknown',
                is_test         INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS relationships (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   TEXT NOT NULL,
                target_id   TEXT NOT NULL,
                kind        TEXT NOT NULL,
                file_path   TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
                start_line  INTEGER,
                start_col   INTEGER,
                end_line    INTEGER,
                end_col     INTEGER,
                confidence  TEXT NOT NULL DEFAULT 'extracted'
            );

            CREATE INDEX IF NOT EXISTS idx_symbols_file    ON symbols(file_path);
            CREATE INDEX IF NOT EXISTS idx_symbols_name    ON symbols(name);
            CREATE INDEX IF NOT EXISTS idx_rels_source     ON relationships(source_id);
            CREATE INDEX IF NOT EXISTS idx_rels_target     ON relationships(target_id);
            CREATE INDEX IF NOT EXISTS idx_rels_kind       ON relationships(kind);
            CREATE INDEX IF NOT EXISTS idx_symbols_is_test ON symbols(is_test);

            CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
                id UNINDEXED,
                name,
                qualified_name,
                docstring,
                signature,
                content=symbols,
                content_rowid=rowid
            );

            CREATE TRIGGER IF NOT EXISTS symbols_fts_insert AFTER INSERT ON symbols BEGIN
                INSERT INTO symbols_fts(rowid, id, name, qualified_name, docstring, signature)
                VALUES (new.rowid, new.id, new.name, new.qualified_name, new.docstring, new.signature);
            END;

            CREATE TRIGGER IF NOT EXISTS symbols_fts_delete AFTER DELETE ON symbols BEGIN
                INSERT INTO symbols_fts(symbols_fts, rowid, id, name, qualified_name, docstring, signature)
                VALUES ('delete', old.rowid, old.id, old.name, old.qualified_name, old.docstring, old.signature);
            END;

            CREATE TRIGGER IF NOT EXISTS symbols_fts_update AFTER UPDATE ON symbols BEGIN
                INSERT INTO symbols_fts(symbols_fts, rowid, id, name, qualified_name, docstring, signature)
                VALUES ('delete', old.rowid, old.id, old.name, old.qualified_name, old.docstring, old.signature);
                INSERT INTO symbols_fts(rowid, id, name, qualified_name, docstring, signature)
                VALUES (new.rowid, new.id, new.name, new.qualified_name, new.docstring, new.signature);
            END;
        """)
        conn.commit()

        # Schema migrations for columns added after initial release
        for stmt in (
            "ALTER TABLE symbols ADD COLUMN is_test INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE files ADD COLUMN is_test INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE relationships ADD COLUMN confidence TEXT NOT NULL DEFAULT 'extracted'",
        ):
            try:
                conn.execute(stmt)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def upsert_parse_result(self, result: ParseResult) -> None:
        """Insert or replace all data from a ParseResult (file, symbols, relationships)."""
        with self._transaction() as conn:
            self._upsert_single(conn, result)

    def upsert_batch(self, results: list[ParseResult]) -> None:
        """Batch insert multiple ParseResults in a single transaction."""
        with self._transaction() as conn:
            for result in results:
                self._upsert_single(conn, result)

    @staticmethod
    def _is_test_file(file_path: str) -> bool:
        """Return True if file_path matches common test file naming conventions."""
        return bool(_TEST_FILE_RE.search(file_path))

    def _upsert_single(self, conn: sqlite3.Connection, result: ParseResult) -> None:
        fi = result.file_info
        is_test = 1 if self._is_test_file(fi.path) else 0
        conn.execute("DELETE FROM files WHERE path = ?", (fi.path,))

        conn.execute(
            """INSERT INTO files(path, language, content_hash, symbol_count,
               relationship_count, size_bytes, is_test) VALUES (?,?,?,?,?,?,?)""",
            (
                fi.path,
                fi.language,
                fi.content_hash,
                fi.symbol_count,
                fi.relationship_count,
                fi.size_bytes,
                is_test,
            ),
        )

        if result.symbols:
            conn.executemany(
                """INSERT OR IGNORE INTO symbols
                   (id, name, qualified_name, kind, file_path,
                    start_line, start_col, end_line, end_col,
                    docstring, signature, decorators, language, is_test)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        sym.id,
                        sym.name,
                        sym.qualified_name,
                        sym.kind.value,
                        sym.file_path,
                        sym.span.start.line,
                        sym.span.start.column,
                        sym.span.end.line,
                        sym.span.end.column,
                        sym.docstring,
                        sym.signature,
                        ",".join(sym.decorators) if sym.decorators else None,
                        sym.language,
                        is_test,
                    )
                    for sym in result.symbols
                ],
            )

        if result.relationships:
            conn.executemany(
                """INSERT INTO relationships
                   (source_id, target_id, kind, file_path,
                    start_line, start_col, end_line, end_col, confidence)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        rel.source_id,
                        rel.target_id,
                        rel.kind.value,
                        rel.file_path,
                        rel.span.start.line if rel.span else None,
                        rel.span.start.column if rel.span else None,
                        rel.span.end.line if rel.span else None,
                        rel.span.end.column if rel.span else None,
                        rel.confidence.value,
                    )
                    for rel in result.relationships
                ],
            )

    def delete_file(self, file_path: str) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM files WHERE path = ?", (file_path,))

    def get_symbol_by_id(self, symbol_id: str) -> Symbol | None:
        """Look up a single symbol by its unique ID."""
        row = self._conn.execute("SELECT * FROM symbols WHERE id = ?", (symbol_id,)).fetchone()
        return self._row_to_symbol(row) if row else None

    def get_symbols_in_file(self, file_path: str) -> list[Symbol]:
        rows = self._conn.execute(
            "SELECT * FROM symbols WHERE file_path = ? ORDER BY start_line",
            (file_path,),
        ).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def find_symbols_by_name(self, name: str, kind: str | None = None) -> list[Symbol]:
        if kind:
            rows = self._conn.execute(
                "SELECT * FROM symbols WHERE name = ? AND kind = ?", (name, kind)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM symbols WHERE name = ?", (name,)).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def get_dependencies(self, symbol_id: str) -> list[Relationship]:
        """Return all relationships where symbol_id is the source (what it depends on)."""
        rows = self._conn.execute(
            "SELECT * FROM relationships WHERE source_id = ?", (symbol_id,)
        ).fetchall()
        return [self._row_to_relationship(r) for r in rows]

    def get_dependents(self, symbol_id: str) -> list[Relationship]:
        """Return all relationships where symbol_id is the target (what depends on it)."""
        rows = self._conn.execute(
            "SELECT * FROM relationships WHERE target_id = ?", (symbol_id,)
        ).fetchall()
        return [self._row_to_relationship(r) for r in rows]

    def trace_call_chain(self, symbol_id: str, max_depth: int = 10) -> list[dict[str, object]]:
        """
        BFS traversal of CALLS relationships starting from symbol_id.
        Returns list of {source_id, target_id, depth} dicts.
        Uses a recursive CTE.
        """
        rows = self._conn.execute(
            """
            WITH RECURSIVE call_chain(source_id, target_id, depth) AS (
                SELECT source_id, target_id, 1
                FROM relationships
                WHERE source_id = ? AND kind = 'calls'
                UNION ALL
                SELECT r.source_id, r.target_id, cc.depth + 1
                FROM relationships r
                JOIN call_chain cc ON r.source_id = cc.target_id
                WHERE r.kind = 'calls' AND cc.depth < ?
            )
            SELECT DISTINCT source_id, target_id, depth FROM call_chain
            ORDER BY depth
            """,
            (symbol_id, max_depth),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_impact_analysis(self, symbol_id: str, max_depth: int = 10) -> list[dict[str, object]]:
        """
        Reverse traversal: what symbols would be affected if symbol_id changes.
        Uses a recursive CTE traversing edges in reverse.
        """
        rows = self._conn.execute(
            """
            WITH RECURSIVE impact(source_id, target_id, depth) AS (
                SELECT source_id, target_id, 1
                FROM relationships
                WHERE target_id = ?
                UNION ALL
                SELECT r.source_id, r.target_id, imp.depth + 1
                FROM relationships r
                JOIN impact imp ON r.target_id = imp.source_id
                WHERE imp.depth < ?
            )
            SELECT DISTINCT source_id, target_id, depth FROM impact
            ORDER BY depth
            """,
            (symbol_id, max_depth),
        ).fetchall()
        return [dict(r) for r in rows]

    def _fts_query(
        self,
        query: str,
        limit: int,
        file_filter: str | None = None,
        kind_filter: str | list[str] | None = None,
    ) -> list[Symbol]:
        """Execute a raw FTS5 query with optional file/kind filters."""
        sql = """
            SELECT s.* FROM symbols s
            JOIN symbols_fts fts ON s.id = fts.id
            WHERE symbols_fts MATCH ?
        """
        params: list[Any] = [query]
        if file_filter:
            sql += " AND s.file_path LIKE ?"
            params.append(f"%{file_filter}%")
        if kind_filter:
            kinds = [kind_filter] if isinstance(kind_filter, str) else list(kind_filter)
            placeholders = ",".join("?" * len(kinds))
            sql += f" AND s.kind IN ({placeholders})"
            params.extend(kinds)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []
        return [self._row_to_symbol(r) for r in rows]

    def _expand_query(self, query: str) -> str:
        """Split underscore_names and CamelCaseNames into space-separated tokens."""
        spaced = query.replace("_", " ")
        spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", spaced)
        return spaced.lower().strip()

    def search(
        self,
        query: str,
        limit: int = 20,
        file_filter: str | None = None,
        kind_filter: str | list[str] | None = None,
    ) -> list[Symbol]:
        """Full-text search over symbol names, docstrings, and signatures.

        Optionally filter results by file path substring or symbol kind.
        ``kind_filter`` accepts a single kind string or a list of kinds.
        Automatically expands camelCase/underscore queries if no results found.
        """
        results = self._fts_query(query, limit, file_filter, kind_filter)
        if results:
            return results
        # Expansion pass 1: split camelCase/underscores and retry
        expanded = self._expand_query(query)
        if expanded != query.lower().strip():
            results = self._fts_query(expanded, limit, file_filter, kind_filter)
        if results:
            return results
        # Expansion pass 2: prefix wildcard on first token
        first_token = query.strip().split()[0] if query.strip() else query
        return self._fts_query(f"{first_token}*", limit, file_filter, kind_filter)

    def get_symbols_by_kind(
        self,
        kind: str,
        file_filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Symbol]:
        """Return all symbols of a given kind, optionally filtered by file path."""
        sql = "SELECT * FROM symbols WHERE kind = ?"
        params: list[Any] = [kind]
        if file_filter:
            sql += " AND file_path LIKE ?"
            params.append(f"%{file_filter}%")
        sql += " ORDER BY file_path, start_line LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(max(0, offset))
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def find_symbols_by_decorator(
        self,
        decorator_name: str,
        file_filter: str | None = None,
        limit: int = 100,
    ) -> list[Symbol]:
        """Return symbols that have a specific decorator/annotation.

        Matches partial decorator names (e.g. 'cached_property' matches '@cached_property').
        """
        sql = "SELECT * FROM symbols WHERE decorators LIKE ?"
        params: list[Any] = [f"%{decorator_name}%"]
        if file_filter:
            sql += " AND file_path LIKE ?"
            params.append(f"%{file_filter}%")
        sql += " ORDER BY file_path, start_line LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def get_stats(self) -> dict[str, int]:
        conn = self._conn
        return {
            "files": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "symbols": conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
            "relationships": conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0],
        }

    def get_language_breakdown(self) -> dict[str, int]:
        """Return symbol counts grouped by language."""
        rows = self._conn.execute(
            "SELECT language, COUNT(*) as cnt FROM symbols GROUP BY language ORDER BY cnt DESC"
        ).fetchall()
        return {row["language"]: row["cnt"] for row in rows}

    def get_kind_breakdown(self) -> dict[str, int]:
        """Return symbol counts grouped by kind (function, class, etc.)."""
        rows = self._conn.execute(
            "SELECT kind, COUNT(*) as cnt FROM symbols GROUP BY kind ORDER BY cnt DESC"
        ).fetchall()
        return {row["kind"]: row["cnt"] for row in rows}

    def list_files(self) -> list[FileInfo]:
        """Return all indexed files."""
        rows = self._conn.execute("SELECT * FROM files ORDER BY path").fetchall()
        return [
            FileInfo(
                path=r["path"],
                language=r["language"],
                content_hash=r["content_hash"],
                symbol_count=r["symbol_count"],
                relationship_count=r["relationship_count"],
                size_bytes=r["size_bytes"],
            )
            for r in rows
        ]

    def get_file_info(self, file_path: str) -> FileInfo | None:
        row = self._conn.execute("SELECT * FROM files WHERE path = ?", (file_path,)).fetchone()
        if row is None:
            return None
        return FileInfo(
            path=row["path"],
            language=row["language"],
            content_hash=row["content_hash"],
            symbol_count=row["symbol_count"],
            relationship_count=row["relationship_count"],
            size_bytes=row["size_bytes"],
        )

    def resolve_imports(self) -> dict[str, int]:
        """Resolve <unresolved>:: and <external>:: targets to actual symbol IDs.

        Uses import-context awareness: when a caller file imports a name, symbols
        from the same directory are preferred over distant matches.
        Returns resolved/unresolved counts.
        """
        stats = {"resolved": 0, "unresolved": 0}
        conn = self._conn

        # Build symbol lookups (exclude import symbols themselves)
        name_to_symbols: dict[str, list[tuple[str, str]]] = {}  # name → [(id, file_path)]
        qname_to_id: dict[str, str] = {}  # qualified_name → id
        for row in conn.execute(
            "SELECT id, name, qualified_name, file_path FROM symbols WHERE kind != 'import'"
        ).fetchall():
            name_to_symbols.setdefault(row["name"], []).append((row["id"], row["file_path"]))
            qname_to_id[row["qualified_name"]] = row["id"]

        # Per-file import context: file_path → set of imported names
        file_import_names: dict[str, set[str]] = {}
        for row in conn.execute(
            "SELECT file_path, name FROM symbols WHERE kind = 'import'"
        ).fetchall():
            file_import_names.setdefault(row["file_path"], set()).add(row["name"])

        # Fetch unresolved relationships with caller file via source symbol
        unresolved_rows = conn.execute(
            """
            SELECT r.id, r.target_id, s.file_path AS caller_file
            FROM relationships r
            JOIN symbols s ON r.source_id = s.id
            WHERE r.target_id LIKE '<external>::%' OR r.target_id LIKE '<unresolved>::%'
            """
        ).fetchall()

        for row in unresolved_rows:
            raw_target: str = row["target_id"]
            rel_id: int = row["id"]
            caller_file: str = row["caller_file"]
            caller_dir = str(Path(caller_file).parent)

            ref_name = (
                raw_target[len("<external>::") :]
                if raw_target.startswith("<external>::")
                else raw_target[len("<unresolved>::") :]
            )
            last_seg = ref_name.rsplit(".", 1)[-1]

            resolved_id: str | None = None
            confidence: str = "inferred"

            # Pass 1: exact qualified name (unique → inferred)
            resolved_id = qname_to_id.get(ref_name)

            # Pass 2: import-scoped — caller explicitly imports this name → prefer same dir
            if resolved_id is None:
                imported = file_import_names.get(caller_file, set())
                candidate_name = (
                    ref_name
                    if ref_name in imported
                    else (last_seg if last_seg in imported else None)
                )
                if candidate_name:
                    candidates = name_to_symbols.get(candidate_name, [])
                    same_dir = [sid for sid, fp in candidates if fp.startswith(caller_dir)]
                    resolved_id = (
                        same_dir[0] if same_dir else (candidates[0][0] if candidates else None)
                    )
                    if resolved_id is not None and len(candidates) > 1:
                        confidence = "ambiguous"

            # Pass 3: last-segment qualified name
            if resolved_id is None and last_seg != ref_name:
                resolved_id = qname_to_id.get(last_seg)

            # Pass 4: global name match, preferring same-directory symbols
            if resolved_id is None:
                candidates = name_to_symbols.get(ref_name) or name_to_symbols.get(last_seg, [])
                if candidates:
                    same_dir = [sid for sid, fp in candidates if fp.startswith(caller_dir)]
                    resolved_id = same_dir[0] if same_dir else candidates[0][0]
                    if len(candidates) > 1:
                        confidence = "ambiguous"

            # If a match was made but multiple symbols share the short name, the
            # heuristic may have silently picked one — tag as ambiguous.
            if (
                resolved_id is not None
                and confidence == "inferred"
                and len(name_to_symbols.get(last_seg, [])) > 1
            ):
                confidence = "ambiguous"

            if resolved_id is not None:
                conn.execute(
                    "UPDATE relationships SET target_id = ?, confidence = ? WHERE id = ?",
                    (resolved_id, confidence, rel_id),
                )
                stats["resolved"] += 1
            else:
                stats["unresolved"] += 1

        conn.commit()
        return stats

    def get_module_overview(self, directory: str) -> dict[str, object]:
        """Summarize all symbols in files under a directory path."""
        conn = self._conn
        rows = conn.execute(
            "SELECT * FROM symbols WHERE file_path LIKE ? ORDER BY file_path, start_line",
            (f"{directory}%",),
        ).fetchall()

        files: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            fp = row["file_path"]
            if fp not in files:
                files[fp] = []
            files[fp].append(
                {
                    "name": row["qualified_name"],
                    "kind": row["kind"],
                }
            )

        return {
            "directory": directory,
            "file_count": len(files),
            "symbol_count": len(rows),
            "files": files,
        }

    def get_file_dependencies(self, file_path: str) -> dict[str, list[str]]:
        """Return what files this file depends on and what files depend on it."""
        conn = self._conn

        # Outgoing: relationships where source is in this file, target is in another file
        outgoing = conn.execute(
            """
            SELECT DISTINCT s2.file_path
            FROM relationships r
            JOIN symbols s1 ON r.source_id = s1.id
            JOIN symbols s2 ON r.target_id = s2.id
            WHERE s1.file_path = ? AND s2.file_path != ?
            """,
            (file_path, file_path),
        ).fetchall()

        # Incoming: relationships where target is in this file, source is in another file
        incoming = conn.execute(
            """
            SELECT DISTINCT s1.file_path
            FROM relationships r
            JOIN symbols s1 ON r.source_id = s1.id
            JOIN symbols s2 ON r.target_id = s2.id
            WHERE s2.file_path = ? AND s1.file_path != ?
            """,
            (file_path, file_path),
        ).fetchall()

        return {
            "depends_on": sorted(row["file_path"] for row in outgoing),
            "depended_by": sorted(row["file_path"] for row in incoming),
        }

    # --- Graph analysis ---

    def detect_cycles(self, relationship_kinds: list[str] | None = None) -> list[list[str]]:
        """Detect circular dependencies in the graph.

        Returns a list of cycles, where each cycle is a list of symbol IDs
        forming a loop (e.g. [A, B, C] means A->B->C->A).
        """
        kinds = relationship_kinds or ["calls", "imports"]
        placeholders = ",".join("?" for _ in kinds)
        conn = self._conn

        # Build adjacency list from relationships
        rows = conn.execute(
            f"SELECT DISTINCT source_id, target_id FROM relationships WHERE kind IN ({placeholders})",
            kinds,
        ).fetchall()

        graph: dict[str, list[str]] = {}
        for row in rows:
            src, tgt = row["source_id"], row["target_id"]
            if tgt.startswith("<external>::") or tgt.startswith("<unresolved>::"):
                continue
            graph.setdefault(src, []).append(tgt)

        # DFS-based cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {node: WHITE for node in graph}
        # Also add nodes that appear only as targets
        all_targets = {tgt for neighbors in graph.values() for tgt in neighbors}
        for t in all_targets:
            if t not in color:
                color[t] = WHITE

        path: list[str] = []
        cycles: list[list[str]] = []
        seen_cycles: set[tuple[str, ...]] = set()

        def dfs(node: str) -> None:
            color[node] = GRAY
            path.append(node)
            for neighbor in graph.get(node, []):
                if color.get(neighbor) == GRAY:
                    # Found a cycle — extract it
                    idx = path.index(neighbor)
                    cycle = path[idx:]
                    # Normalize: rotate so smallest ID is first (for dedup)
                    min_idx = cycle.index(min(cycle))
                    normalized = tuple(cycle[min_idx:] + cycle[:min_idx])
                    if normalized not in seen_cycles:
                        seen_cycles.add(normalized)
                        cycles.append(list(normalized))
                elif color.get(neighbor, WHITE) == WHITE:
                    dfs(neighbor)
            path.pop()
            color[node] = BLACK

        for node in list(graph.keys()):
            if color.get(node) == WHITE:
                dfs(node)

        return cycles

    def find_unused_symbols(self, include_tests: bool = False) -> list[Symbol]:
        """Find symbols with no incoming relationships (potential dead code).

        Excludes modules, imports, common entry points, and test symbols by default.
        Set include_tests=True to include symbols from test files.
        """
        conn = self._conn
        sql = """
            SELECT s.* FROM symbols s
            LEFT JOIN relationships r ON r.target_id = s.id
            WHERE r.id IS NULL
              AND s.kind NOT IN ('module', 'import')
              AND s.name NOT IN ('__init__', 'main', 'cli', '__main__')
        """
        if not include_tests:
            sql += " AND s.is_test = 0"
        sql += " ORDER BY s.file_path, s.start_line"
        rows = conn.execute(sql).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def get_symbol_centrality(self, limit: int = 50) -> list[dict[str, object]]:
        """Compute degree centrality for each symbol.

        Returns symbols sorted by total degree (in + out), highest first.
        """
        conn = self._conn
        rows = conn.execute(
            """
            SELECT
                s.id,
                s.name,
                s.qualified_name,
                s.kind,
                s.file_path,
                COALESCE(out_deg.cnt, 0) as out_degree,
                COALESCE(in_deg.cnt, 0) as in_degree,
                COALESCE(out_deg.cnt, 0) + COALESCE(in_deg.cnt, 0) as total_degree
            FROM symbols s
            LEFT JOIN (
                SELECT source_id, COUNT(*) as cnt FROM relationships GROUP BY source_id
            ) out_deg ON out_deg.source_id = s.id
            LEFT JOIN (
                SELECT target_id, COUNT(*) as cnt FROM relationships GROUP BY target_id
            ) in_deg ON in_deg.target_id = s.id
            WHERE COALESCE(out_deg.cnt, 0) + COALESCE(in_deg.cnt, 0) > 0
            ORDER BY total_degree DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "qualified_name": r["qualified_name"],
                "kind": r["kind"],
                "file": r["file_path"],
                "in_degree": r["in_degree"],
                "out_degree": r["out_degree"],
                "total_degree": r["total_degree"],
            }
            for r in rows
        ]

    def find_path(self, source_id: str, target_id: str, max_depth: int = 10) -> list[str] | None:
        """Find the shortest path between two symbols using BFS.

        Returns list of symbol IDs forming the path (inclusive), or None if no path exists.
        """
        if source_id == target_id:
            return [source_id]

        conn = self._conn
        # Build adjacency list
        rows = conn.execute("SELECT DISTINCT source_id, target_id FROM relationships").fetchall()

        graph: dict[str, list[str]] = {}
        for row in rows:
            src, tgt = row["source_id"], row["target_id"]
            if tgt.startswith("<external>::") or tgt.startswith("<unresolved>::"):
                continue
            graph.setdefault(src, []).append(tgt)

        # BFS
        from collections import deque

        queue: deque[list[str]] = deque([[source_id]])
        visited: set[str] = {source_id}

        while queue:
            path = queue.popleft()
            node = path[-1]
            # len(path) - 1 is the number of edges so far
            if len(path) - 1 >= max_depth:
                continue
            for neighbor in graph.get(node, []):
                if neighbor == target_id:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])

        return None

    def get_file_coupling(self, limit: int = 20) -> list[dict[str, Any]]:
        """Compute coupling between file pairs based on cross-file relationships.

        Returns file pairs sorted by the number of relationships between them.
        """
        conn = self._conn
        rows = conn.execute(
            """
            SELECT
                s1.file_path as source_file,
                s2.file_path as target_file,
                COUNT(*) as relationship_count,
                GROUP_CONCAT(DISTINCT r.kind) as relationship_kinds
            FROM relationships r
            JOIN symbols s1 ON r.source_id = s1.id
            JOIN symbols s2 ON r.target_id = s2.id
            WHERE s1.file_path != s2.file_path
            GROUP BY s1.file_path, s2.file_path
            ORDER BY relationship_count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "source_file": r["source_file"],
                "target_file": r["target_file"],
                "relationship_count": r["relationship_count"],
                "kinds": r["relationship_kinds"].split(",") if r["relationship_kinds"] else [],
            }
            for r in rows
        ]

    def get_affected_files(self, file_path: str) -> list[str]:
        """If this file changes, what other files might be affected?"""
        conn = self._conn
        rows = conn.execute(
            """
            SELECT DISTINCT s1.file_path
            FROM relationships r
            JOIN symbols s2 ON r.target_id = s2.id
            JOIN symbols s1 ON r.source_id = s1.id
            WHERE s2.file_path = ? AND s1.file_path != ?
            """,
            (file_path, file_path),
        ).fetchall()
        return sorted(row["file_path"] for row in rows)

    def get_hotspots(self, repo_path: str | Path, limit: int = 20) -> list[dict[str, Any]]:
        """Return files ranked by git churn × graph in-degree.

        Combines how often a file changes in git with how many other symbols
        depend on it, surfacing the highest-risk code for review.
        """
        from codeatlas.git_integration import get_git_churn

        churn = get_git_churn(Path(repo_path), limit=200)
        if not churn:
            return []

        conn = self._conn
        results: list[dict[str, Any]] = []
        for entry in churn:
            fp = entry["file"]
            row = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT s.id) as symbol_count,
                    COALESCE(SUM(in_deg.cnt), 0) as total_in_degree
                FROM symbols s
                LEFT JOIN (
                    SELECT target_id, COUNT(*) as cnt
                    FROM relationships GROUP BY target_id
                ) in_deg ON in_deg.target_id = s.id
                WHERE s.file_path = ? OR s.file_path LIKE ?
                """,
                (fp, f"%/{fp}"),
            ).fetchone()
            commits = entry["commits"]
            in_degree = int(row["total_in_degree"]) if row else 0
            symbol_count = int(row["symbol_count"]) if row else 0
            score = commits * (1 + in_degree)
            results.append(
                {
                    "file": fp,
                    "commits": commits,
                    "in_degree": in_degree,
                    "symbol_count": symbol_count,
                    "hotspot_score": score,
                }
            )

        results.sort(key=lambda x: -x["hotspot_score"])
        return results[:limit]

    def get_symbol_coverage(self, symbol_name: str) -> dict[str, Any]:
        """Find which test functions/files reference a given symbol.

        Uses the is_test flag to identify test-file callers, giving a quick
        picture of whether a symbol has direct test coverage.
        """
        syms = self.find_symbols_by_name(symbol_name)
        if not syms:
            return {"error": f"Symbol '{symbol_name}' not found", "results": []}

        conn = self._conn
        results: list[dict[str, Any]] = []
        for sym in syms:
            rows = conn.execute(
                """
                SELECT DISTINCT s.name, s.qualified_name, s.kind, s.file_path,
                       s.start_line, r.kind as rel_kind
                FROM relationships r
                JOIN symbols s ON r.source_id = s.id
                WHERE r.target_id = ? AND s.is_test = 1
                ORDER BY s.file_path, s.start_line
                """,
                (sym.id,),
            ).fetchall()
            test_refs = [
                {
                    "name": r["name"],
                    "qualified_name": r["qualified_name"],
                    "kind": r["kind"],
                    "file": r["file_path"],
                    "line": r["start_line"],
                    "relationship": r["rel_kind"],
                }
                for r in rows
            ]
            results.append(
                {
                    "symbol": sym.qualified_name,
                    "kind": sym.kind.value,
                    "file": sym.file_path,
                    "is_test": sym.is_test,
                    "test_references": test_refs,
                    "covered": len(test_refs) > 0,
                }
            )

        return {"results": results, "total_symbols": len(results)}

    def get_api_surface(
        self,
        file_filter: str | None = None,
        limit: int = 200,
    ) -> list[Symbol]:
        """Return public non-test symbols (excludes leading-underscore names and imports/variables).

        Useful for generating documentation or understanding the exported API of a codebase.
        """
        conn = self._conn
        params: list[Any] = []
        sql = """
            SELECT * FROM symbols
            WHERE is_test = 0
              AND name NOT LIKE '\\_%' ESCAPE '\\'
              AND kind NOT IN ('import', 'variable')
        """
        if file_filter:
            sql += " AND file_path LIKE ?"
            params.append(f"{file_filter}%")
        sql += " ORDER BY file_path, start_line LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def get_coverage_gaps(
        self,
        file_filter: str | None = None,
        limit: int = 200,
    ) -> list[Symbol]:
        """Return public non-test symbols that have zero test-file references.

        These are the symbols most at risk — they're part of the public API but no
        test function calls or imports them. Useful for prioritising where to write tests.
        """
        conn = self._conn
        params: list[Any] = []
        sql = """
            SELECT * FROM symbols s
            WHERE s.is_test = 0
              AND s.name NOT LIKE '\\_%' ESCAPE '\\'
              AND s.kind NOT IN ('import', 'variable')
              AND NOT EXISTS (
                  SELECT 1 FROM relationships r
                  JOIN symbols src ON r.source_id = src.id
                  WHERE r.target_id = s.id AND src.is_test = 1
              )
        """
        if file_filter:
            sql += " AND s.file_path LIKE ?"
            params.append(f"{file_filter}%")
        sql += " ORDER BY s.file_path, s.start_line LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def get_confidence_stats(self) -> dict[str, int]:
        """Return a breakdown of relationship counts by confidence level.

        Keys are confidence values (``extracted``, ``inferred``, ``ambiguous``).
        Missing keys default to 0 so callers can unconditionally index.
        """
        conn = self._conn
        rows = conn.execute(
            "SELECT confidence, COUNT(*) AS cnt FROM relationships GROUP BY confidence"
        ).fetchall()
        stats = {"extracted": 0, "inferred": 0, "ambiguous": 0}
        for r in rows:
            key = r["confidence"] or "extracted"
            stats[key] = r["cnt"]
        return stats

    def detect_communities(self, max_iterations: int = 30) -> dict[str, str]:
        """Group symbols into communities via label propagation.

        Treats the relationship graph as undirected and runs the synchronous
        label-propagation algorithm: each node starts with its own label, then
        repeatedly adopts the most common label among its neighbors until no
        labels change or ``max_iterations`` is reached.

        Returns a mapping of ``symbol_id`` → ``community_id`` (the label of a
        seed member in the same community).

        No external dependencies; O(V + E) per iteration.
        """
        conn = self._conn
        # Build an undirected adjacency map, skipping external/unresolved nodes
        adj: dict[str, set[str]] = {}
        for row in conn.execute(
            """
            SELECT r.source_id, r.target_id
            FROM relationships r
            JOIN symbols s1 ON s1.id = r.source_id
            JOIN symbols s2 ON s2.id = r.target_id
            """
        ).fetchall():
            src: str = row["source_id"]
            tgt: str = row["target_id"]
            if src == tgt:
                continue
            adj.setdefault(src, set()).add(tgt)
            adj.setdefault(tgt, set()).add(src)

        if not adj:
            return {}

        # Initialize: each node is its own community
        labels: dict[str, str] = {node: node for node in adj}

        # Iterate in a deterministic order so results are reproducible
        node_order = sorted(adj.keys())
        for _ in range(max_iterations):
            changed = False
            for node in node_order:
                neighbors = adj[node]
                if not neighbors:
                    continue
                # Count labels among neighbors
                counts: dict[str, int] = {}
                for nb in neighbors:
                    lbl = labels[nb]
                    counts[lbl] = counts.get(lbl, 0) + 1
                # Pick the most common label, tiebreak by lexicographic order
                best_label = max(counts.items(), key=lambda kv: (kv[1], -hash(kv[0])))[0]
                if labels[node] != best_label:
                    labels[node] = best_label
                    changed = True
            if not changed:
                break
        return labels

    def get_community_summary(self, min_size: int = 2) -> list[dict[str, Any]]:
        """Summarize communities: community_id, size, representative members.

        Only communities with at least ``min_size`` members are returned,
        sorted by size descending.
        """
        labels = self.detect_communities()
        if not labels:
            return []

        groups: dict[str, list[str]] = {}
        for node, lbl in labels.items():
            groups.setdefault(lbl, []).append(node)

        conn = self._conn
        summaries: list[dict[str, Any]] = []
        for lbl, members in groups.items():
            if len(members) < min_size:
                continue
            # Fetch names for up to 5 representative members
            placeholders = ",".join("?" * min(len(members), 5))
            sample_rows = conn.execute(
                f"SELECT qualified_name, file_path FROM symbols WHERE id IN ({placeholders})",
                members[:5],
            ).fetchall()
            summaries.append(
                {
                    "community_id": lbl,
                    "size": len(members),
                    "sample": [
                        {"name": r["qualified_name"], "file": r["file_path"]} for r in sample_rows
                    ],
                }
            )
        summaries.sort(key=lambda d: (-int(d["size"]), str(d["community_id"])))
        return summaries

    def get_hub_symbols(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most-connected symbols ("god nodes") in the graph.

        Combines in-degree (how many symbols depend on this one) and out-degree
        (how many other symbols it calls). Symbols with unusually high total
        degree are likely load-bearing — modifying them has wide blast radius.
        """
        conn = self._conn
        sql = """
            SELECT
                s.id AS id,
                s.name AS name,
                s.qualified_name AS qualified_name,
                s.kind AS kind,
                s.file_path AS file_path,
                s.start_line AS start_line,
                COALESCE(outgoing.cnt, 0) AS out_degree,
                COALESCE(incoming.cnt, 0) AS in_degree,
                COALESCE(outgoing.cnt, 0) + COALESCE(incoming.cnt, 0) AS total_degree
            FROM symbols s
            LEFT JOIN (
                SELECT source_id, COUNT(*) AS cnt FROM relationships GROUP BY source_id
            ) outgoing ON outgoing.source_id = s.id
            LEFT JOIN (
                SELECT target_id, COUNT(*) AS cnt FROM relationships GROUP BY target_id
            ) incoming ON incoming.target_id = s.id
            WHERE s.kind NOT IN ('import', 'variable')
            ORDER BY total_degree DESC, s.name ASC
            LIMIT ?
        """
        rows = conn.execute(sql, (limit,)).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "qualified_name": r["qualified_name"],
                "kind": r["kind"],
                "file": r["file_path"],
                "line": r["start_line"] + 1,
                "in_degree": r["in_degree"],
                "out_degree": r["out_degree"],
                "total_degree": r["total_degree"],
            }
            for r in rows
            if r["total_degree"] > 0
        ]

    def compute_pagerank(
        self,
        damping: float = 0.85,
        max_iterations: int = 50,
        tolerance: float = 1e-6,
    ) -> dict[str, float]:
        """Compute PageRank over the symbol graph.

        Direction: edges flow source -> target, so a symbol that is
        called/imported/inherited a lot accumulates rank. Runs in pure
        Python so there is no NumPy/networkx dependency.

        Returns an empty dict when the graph has no edges.
        """
        conn = self._conn
        node_ids: set[str] = {row["id"] for row in conn.execute("SELECT id FROM symbols")}
        if not node_ids:
            return {}
        out_links: dict[str, list[str]] = {}
        in_links: dict[str, list[str]] = {}
        for row in conn.execute("SELECT source_id, target_id FROM relationships"):
            src = row["source_id"]
            tgt = row["target_id"]
            if src not in node_ids or tgt not in node_ids:
                continue
            if src == tgt:
                continue
            out_links.setdefault(src, []).append(tgt)
            in_links.setdefault(tgt, []).append(src)
        if not in_links:
            return {}

        n = len(node_ids)
        rank = dict.fromkeys(node_ids, 1.0 / n)
        base = (1.0 - damping) / n
        for _ in range(max_iterations):
            dangling_sum = sum(rank[nid] for nid in node_ids if nid not in out_links)
            dangling_share = damping * dangling_sum / n
            new_rank: dict[str, float] = {}
            for node in node_ids:
                s = 0.0
                for src in in_links.get(node, []):
                    s += rank[src] / len(out_links[src])
                new_rank[node] = base + dangling_share + damping * s
            delta = sum(abs(new_rank[k] - rank[k]) for k in node_ids)
            rank = new_rank
            if delta < tolerance:
                break
        return rank

    def get_pagerank_ranking(
        self, limit: int = 20, kind_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Return the top-N symbols ranked by PageRank (highest first)."""
        ranks = self.compute_pagerank()
        if not ranks:
            return []
        top_ids = sorted(ranks.items(), key=lambda kv: kv[1], reverse=True)
        conn = self._conn
        results: list[dict[str, Any]] = []
        for sym_id, score in top_ids:
            if len(results) >= limit:
                break
            row = conn.execute(
                """SELECT id, name, qualified_name, kind, file_path, start_line
                   FROM symbols WHERE id = ?""",
                (sym_id,),
            ).fetchone()
            if row is None:
                continue
            if kind_filter and row["kind"] != kind_filter:
                continue
            results.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "qualified_name": row["qualified_name"],
                    "kind": row["kind"],
                    "file": row["file_path"],
                    "line": row["start_line"] + 1,
                    "score": round(float(score), 6),
                }
            )
        return results

    def close(self) -> None:
        self._conn.close()

    # --- Private helpers ---

    def _row_to_symbol(self, row: sqlite3.Row) -> Symbol:
        from codeatlas.models import Position, Span, SymbolKind

        keys = row.keys()
        return Symbol(
            id=row["id"],
            name=row["name"],
            qualified_name=row["qualified_name"],
            kind=SymbolKind(row["kind"]),
            file_path=row["file_path"],
            span=Span(
                start=Position(line=row["start_line"], column=row["start_col"]),
                end=Position(line=row["end_line"], column=row["end_col"]),
            ),
            docstring=row["docstring"],
            signature=row["signature"],
            decorators=row["decorators"].split(",") if row["decorators"] else [],
            language=row["language"],
            is_test=bool(row["is_test"]) if "is_test" in keys else False,
        )

    def _row_to_relationship(self, row: sqlite3.Row) -> Relationship:
        from codeatlas.models import Confidence, Position, RelationshipKind, Span

        span = None
        if row["start_line"] is not None:
            span = Span(
                start=Position(line=row["start_line"], column=row["start_col"]),
                end=Position(line=row["end_line"], column=row["end_col"]),
            )
        keys = row.keys()
        confidence = Confidence(row["confidence"]) if "confidence" in keys else Confidence.EXTRACTED
        return Relationship(
            source_id=row["source_id"],
            target_id=row["target_id"],
            kind=RelationshipKind(row["kind"]),
            file_path=row["file_path"],
            span=span,
            confidence=confidence,
        )
