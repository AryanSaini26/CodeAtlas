"""SQLite-backed code knowledge graph store."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

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
            fi = result.file_info
            # Delete existing data for this file (cascade deletes symbols+rels)
            conn.execute("DELETE FROM files WHERE path = ?", (fi.path,))

            conn.execute(
                """INSERT INTO files(path, language, content_hash, symbol_count,
                   relationship_count, size_bytes) VALUES (?,?,?,?,?,?)""",
                (fi.path, fi.language, fi.content_hash,
                 fi.symbol_count, fi.relationship_count, fi.size_bytes),
            )

            for sym in result.symbols:
                conn.execute(
                    """INSERT OR REPLACE INTO symbols
                       (id, name, qualified_name, kind, file_path,
                        start_line, start_col, end_line, end_col,
                        docstring, signature, decorators, language)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        sym.id, sym.name, sym.qualified_name, sym.kind.value,
                        sym.file_path,
                        sym.span.start.line, sym.span.start.column,
                        sym.span.end.line, sym.span.end.column,
                        sym.docstring, sym.signature,
                        ",".join(sym.decorators) if sym.decorators else None,
                        sym.language,
                    ),
                )

            for rel in result.relationships:
                conn.execute(
                    """INSERT INTO relationships
                       (source_id, target_id, kind, file_path,
                        start_line, start_col, end_line, end_col)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        rel.source_id, rel.target_id, rel.kind.value, rel.file_path,
                        rel.span.start.line if rel.span else None,
                        rel.span.start.column if rel.span else None,
                        rel.span.end.line if rel.span else None,
                        rel.span.end.column if rel.span else None,
                    ),
                )

    def delete_file(self, file_path: str) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM files WHERE path = ?", (file_path,))

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
            rows = self._conn.execute(
                "SELECT * FROM symbols WHERE name = ?", (name,)
            ).fetchall()
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

    def get_file_info(self, file_path: str) -> FileInfo | None:
        row = self._conn.execute(
            "SELECT * FROM files WHERE path = ?", (file_path,)
        ).fetchone()
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
