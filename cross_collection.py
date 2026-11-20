"""Helpers for reviewed cross-collection narration relationships."""
from __future__ import annotations
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def apply_migration(db_path: str | Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript((ROOT / "cross_collection_schema.sql").read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()

def get_related_narrations(db_path: str | Path, hadith_id: int) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
          SELECT h.id,h.hadith_key,h.hadith_number,c.collection_name_en,
                 x.relation_type,x.confidence,x.evidence_note,x.review_status
          FROM hadith_cross_references x
          JOIN hadith_records h ON h.id =
            CASE WHEN x.from_hadith_id=? THEN x.to_hadith_id ELSE x.from_hadith_id END
          JOIN collections c ON c.id=h.collection_id
          WHERE (x.from_hadith_id=? OR x.to_hadith_id=?)
            AND x.review_status='reviewed'
          ORDER BY c.collection_name_en,h.hadith_number
        """,(hadith_id,hadith_id,hadith_id)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_independent_chains(db_path: str | Path, hadith_id: int) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute("""
          SELECT * FROM hadith_chains WHERE hadith_id=? ORDER BY id
        """,(hadith_id,)).fetchall()]
    finally:
        conn.close()
