#!/usr/bin/env python3
"""Add a normalized Arabic/Urdu-friendly FTS5 index to bukhari_fts.db.

The original passages.text column is never changed. The extra search copy
strips Arabic diacritics and normalizes common letter variants for retrieval.
Run once offline before deployment:
    python build_normalized_search_index.py
"""
from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "bukhari_fts.db"


def normalize_search_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(
        char for char in value
        if unicodedata.category(char) not in {"Mn", "Me"} and char != "ـ"
    )
    table = str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ئ": "ي", "ؤ": "و",
        "ی": "ي", "ے": "ي", "ک": "ك",
    })
    return value.translate(table).casefold()


def main() -> None:
    if not DB_PATH.is_file():
        raise SystemExit(f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS passages_search_text (
                id INTEGER PRIMARY KEY REFERENCES passages(id),
                text TEXT NOT NULL
            )
        """)
        existing = conn.execute("SELECT COUNT(*) FROM passages_search_text").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        if existing != total:
            conn.execute("DELETE FROM passages_search_text")
            rows = conn.execute("SELECT id, text FROM passages ORDER BY id").fetchall()
            conn.executemany(
                "INSERT INTO passages_search_text(id, text) VALUES (?, ?)",
                [(row[0], normalize_search_text(row[1])) for row in rows],
            )
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts_normalized USING fts5(
                text,
                content='passages_search_text',
                content_rowid='id',
                tokenize='unicode61 remove_diacritics 2'
            )
        """)
        # External-content FTS tables report their content-table row count even
        # before their inverted index is populated. Rebuild explicitly every run.
        conn.execute("INSERT INTO passages_fts_normalized(passages_fts_normalized) VALUES('rebuild')")
        conn.execute("INSERT INTO passages_fts_normalized(passages_fts_normalized) VALUES('optimize')")
        indexed = conn.execute(
            "SELECT COUNT(*) FROM passages_search_text"
        ).fetchone()[0]
        conn.commit()
        print(f"Normalized FTS index ready: {indexed:,} passage records")
        print(f"Database size: {DB_PATH.stat().st_size / (1024 * 1024):.1f} MiB")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
