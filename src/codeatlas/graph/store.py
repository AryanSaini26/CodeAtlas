"""SQLite-backed code knowledge graph store."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from codeatlas.models import FileInfo, ParseResult, Relationship, Symbol


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
                indexed_at  REAL DEFAULT (unixepoch('now', 'subsec'))
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
                language        TEXT NOT NULL DEFAULT 'unknown'
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
                end_col     INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_symbols_file    ON symbols(file_path);
            CREATE INDEX IF NOT EXISTS idx_symbols_name    ON symbols(name);
            CREATE INDEX IF NOT EXISTS idx_rels_source     ON relationships(source_id);
            CREATE INDEX IF NOT EXISTS idx_rels_target     ON relationships(target_id);
            CREATE INDEX IF NOT EXISTS idx_rels_kind       ON relationships(kind);

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

    def _upsert_single(self, conn: sqlite3.Connection, result: ParseResult) -> None:
        fi = result.file_info
        conn.execute("DELETE FROM files WHERE path = ?", (fi.path,))

        conn.execute(
            """INSERT INTO files(path, language, content_hash, symbol_count,
               relationship_count, size_bytes) VALUES (?,?,?,?,?,?)""",
            (
                fi.path,
                fi.language,
                fi.content_hash,
                fi.symbol_count,
                fi.relationship_count,
                fi.size_bytes,
            ),
        )

        if result.symbols:
            conn.executemany(
                """INSERT OR REPLACE INTO symbols
                   (id, name, qualified_name, kind, file_path,
                    start_line, start_col, end_line, end_col,
                    docstring, signature, decorators, language)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    )
                    for sym in result.symbols
                ],
            )

        if result.relationships:
            conn.executemany(
                """INSERT INTO relationships
                   (source_id, target_id, kind, file_path,
                    start_line, start_col, end_line, end_col)
                   VALUES (?,?,?,?,?,?,?,?)""",
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

    def search(self, query: str, limit: int = 20) -> list[Symbol]:
        """Full-text search over symbol names, docstrings, and signatures."""
        rows = self._conn.execute(
            """
            SELECT s.* FROM symbols s
            JOIN symbols_fts fts ON s.id = fts.id
            WHERE symbols_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
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
        """Resolve <external>:: and <unresolved>:: targets to actual symbol IDs in the graph.

        After indexing all files, run this to link cross-file references.
        Returns counts of resolved vs unresolved references.
        """
        stats = {"resolved": 0, "unresolved": 0}
        conn = self._conn

        # Build a lookup of symbol name -> id for resolution
        symbol_lookup: dict[str, str] = {}
        rows = conn.execute("SELECT id, name, qualified_name FROM symbols").fetchall()
        for row in rows:
            symbol_lookup[row["name"]] = row["id"]
            symbol_lookup[row["qualified_name"]] = row["id"]

        # Find all unresolved targets
        unresolved_rows = conn.execute(
            "SELECT id, target_id FROM relationships WHERE target_id LIKE '<external>::%' OR target_id LIKE '<unresolved>::%'"
        ).fetchall()

        for row in unresolved_rows:
            raw_target = row["target_id"]
            # Strip the prefix
            if raw_target.startswith("<external>::"):
                ref_name = raw_target[len("<external>::") :]
            else:
                ref_name = raw_target[len("<unresolved>::") :]

            # Try exact match, then last segment
            resolved_id = symbol_lookup.get(ref_name)
            if resolved_id is None:
                # Try the last segment (e.g., "os.path.join" -> "join")
                last_segment = ref_name.rsplit(".", 1)[-1]
                resolved_id = symbol_lookup.get(last_segment)

            if resolved_id is not None:
                conn.execute(
                    "UPDATE relationships SET target_id = ? WHERE id = ?",
                    (resolved_id, row["id"]),
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

    def find_unused_symbols(self) -> list[Symbol]:
        """Find symbols with no incoming relationships (potential dead code).

        Excludes modules, imports, and common entry points (__init__, main, cli).
        """
        conn = self._conn
        rows = conn.execute(
            """
            SELECT s.* FROM symbols s
            LEFT JOIN relationships r ON r.target_id = s.id
            WHERE r.id IS NULL
              AND s.kind NOT IN ('module', 'import')
              AND s.name NOT IN ('__init__', 'main', 'cli', '__main__')
            ORDER BY s.file_path, s.start_line
            """
        ).fetchall()
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

    def close(self) -> None:
        self._conn.close()

    # --- Private helpers ---

    def _row_to_symbol(self, row: sqlite3.Row) -> Symbol:
        from codeatlas.models import Position, Span, SymbolKind

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
        )

    def _row_to_relationship(self, row: sqlite3.Row) -> Relationship:
        from codeatlas.models import Position, RelationshipKind, Span

        span = None
        if row["start_line"] is not None:
            span = Span(
                start=Position(line=row["start_line"], column=row["start_col"]),
                end=Position(line=row["end_line"], column=row["end_col"]),
            )
        return Relationship(
            source_id=row["source_id"],
            target_id=row["target_id"],
            kind=RelationshipKind(row["kind"]),
            file_path=row["file_path"],
            span=span,
        )
