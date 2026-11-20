#!/usr/bin/env python3
"""Import reviewed, structured hadith records from JSONL into SQLite.

Each JSONL line is one edition-specific narration record. The importer never
creates translations, splits isnad/matn, or assigns grades automatically.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "hadith_schema.sql"


def normalize_search_text(text: str) -> str:
    """Normalize Arabic/Urdu for FTS only; source fields stay unchanged."""
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


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Required field {field!r} must be a non-empty string")
    return value.strip()


def connect_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def get_collection_id(conn: sqlite3.Connection, record: dict[str, Any]) -> int:
    slug = require_text(record.get("collection_slug"), "collection_slug")
    name_en = require_text(record.get("collection_name_en"), "collection_name_en")
    name_ar = (record.get("collection_name_ar") or "").strip()
    conn.execute(
        "INSERT OR IGNORE INTO collections(collection_slug, collection_name_en, collection_name_ar) VALUES (?, ?, ?)",
        (slug, name_en, name_ar),
    )
    row = conn.execute("SELECT id FROM collections WHERE collection_slug = ?", (slug,)).fetchone()
    return int(row[0])


def get_edition_id(conn: sqlite3.Connection, collection_id: int, edition: dict[str, Any] | None) -> int | None:
    if not edition:
        return None
    edition_slug = require_text(edition.get("edition_slug"), "edition.edition_slug")
    label = require_text(edition.get("edition_label"), "edition.edition_label")
    language = require_text(edition.get("language"), "edition.language").lower()
    if language not in {"ar", "ur", "en", "other"}:
        raise ValueError("edition.language must be ar, ur, en, or other")
    values = (
        collection_id, edition_slug, label, language,
        edition.get("translator"), edition.get("editor"), edition.get("researcher"),
        edition.get("publisher"), str(edition.get("publication_year") or ""),
        edition.get("archive_identifier"), edition.get("source_url"),
        edition.get("rights_status") or "unverified", edition.get("notes"),
    )
    conn.execute(
        """INSERT OR IGNORE INTO editions(
            collection_id, edition_slug, edition_label, language, translator,
            editor, researcher, publisher, publication_year, archive_identifier,
            source_url, rights_status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        values,
    )
    row = conn.execute(
        "SELECT id FROM editions WHERE collection_id = ? AND edition_slug = ? AND language = ?",
        (collection_id, edition_slug, language),
    ).fetchone()
    return int(row[0])


def refresh_search_document(conn: sqlite3.Connection, hadith_id: int) -> None:
    row = conn.execute(
        """SELECT h.hadith_number, h.book_title, h.chapter_title, h.arabic_full,
                  h.isnad_ar, h.matn_ar, c.collection_name_en, c.collection_name_ar
           FROM hadith_records h JOIN collections c ON c.id = h.collection_id
           WHERE h.id = ?""",
        (hadith_id,),
    ).fetchone()
    translations = conn.execute(
        "SELECT language, translation_text FROM hadith_translations WHERE hadith_id = ?",
        (hadith_id,),
    ).fetchall()
    grades = conn.execute(
        "SELECT grade_label_original, grade_normalized, grader_name, grading_source FROM hadith_grades WHERE hadith_id = ?",
        (hadith_id,),
    ).fetchall()
    translation_text = "\n".join(f"{t['language']}: {t['translation_text']}" for t in translations)
    grade_text = "\n".join(
        " — ".join(part for part in (g["grade_normalized"], g["grade_label_original"], g["grader_name"], g["grading_source"]) if part)
        for g in grades
    )
    conn.execute(
        """INSERT INTO hadith_search_documents(
            hadith_id, collection_text, hadith_number, book_title, chapter_title,
            arabic_full, isnad_ar, matn_ar, translation_text, grade_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hadith_id) DO UPDATE SET
            collection_text=excluded.collection_text,
            hadith_number=excluded.hadith_number,
            book_title=excluded.book_title,
            chapter_title=excluded.chapter_title,
            arabic_full=excluded.arabic_full,
            isnad_ar=excluded.isnad_ar,
            matn_ar=excluded.matn_ar,
            translation_text=excluded.translation_text,
            grade_text=excluded.grade_text""",
        (
            hadith_id,
            normalize_search_text(f"{row['collection_name_en']} {row['collection_name_ar'] or ''}"),
            normalize_search_text(row["hadith_number"]),
            normalize_search_text(row["book_title"] or ""),
            normalize_search_text(row["chapter_title"] or ""),
            normalize_search_text(row["arabic_full"] or ""),
            normalize_search_text(row["isnad_ar"] or ""),
            normalize_search_text(row["matn_ar"] or ""),
            normalize_search_text(translation_text),
            normalize_search_text(grade_text),
        ),
    )


def import_record(conn: sqlite3.Connection, record: dict[str, Any]) -> int:
    collection_id = get_collection_id(conn, record)
    edition_id = get_edition_id(conn, collection_id, record.get("edition"))
    hadith_key = require_text(record.get("hadith_key"), "hadith_key")
    hadith_number = require_text(str(record.get("hadith_number", "")), "hadith_number")
    source = record.get("source") or {}

    conn.execute(
        """INSERT INTO hadith_records(
            hadith_key, collection_id, edition_id, hadith_number, book_number,
            book_title, chapter_number, chapter_title, arabic_full, isnad_ar,
            matn_ar, source_volume, source_page_start, source_page_end,
            source_reference, source_url, transcription_status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hadith_key) DO UPDATE SET
            collection_id=excluded.collection_id,
            edition_id=excluded.edition_id,
            hadith_number=excluded.hadith_number,
            book_number=excluded.book_number,
            book_title=excluded.book_title,
            chapter_number=excluded.chapter_number,
            chapter_title=excluded.chapter_title,
            arabic_full=excluded.arabic_full,
            isnad_ar=excluded.isnad_ar,
            matn_ar=excluded.matn_ar,
            source_volume=excluded.source_volume,
            source_page_start=excluded.source_page_start,
            source_page_end=excluded.source_page_end,
            source_reference=excluded.source_reference,
            source_url=excluded.source_url,
            transcription_status=excluded.transcription_status,
            notes=excluded.notes""",
        (
            hadith_key, collection_id, edition_id, hadith_number,
            record.get("book_number"), record.get("book_title"),
            record.get("chapter_number"), record.get("chapter_title"),
            record.get("arabic_full"), record.get("isnad_ar"), record.get("matn_ar"),
            str(source.get("volume") or ""), str(source.get("page_start") or ""),
            str(source.get("page_end") or ""), source.get("reference"),
            source.get("url"), record.get("transcription_status") or "unverified",
            record.get("notes"),
        ),
    )
    hadith_id = int(conn.execute("SELECT id FROM hadith_records WHERE hadith_key = ?", (hadith_key,)).fetchone()[0])

    # Reimport idempotently by replacing child rows for this hadith.
    conn.execute("DELETE FROM hadith_translations WHERE hadith_id = ?", (hadith_id,))
    conn.execute("DELETE FROM hadith_grades WHERE hadith_id = ?", (hadith_id,))

    for translation in record.get("translations", []):
        language = require_text(translation.get("language"), "translation.language").lower()
        translation_edition_id = get_edition_id(
            conn, collection_id, translation.get("edition")
        )
        if language not in {"ar", "ur", "en", "other"}:
            raise ValueError("translation.language must be ar, ur, en, or other")
        translation_text = require_text(translation.get("translation_text"), "translation.translation_text")
        conn.execute(
            """INSERT INTO hadith_translations(
                hadith_id, edition_id, language, translation_text, translator,
                edition_label, volume, page, rights_status, source_url, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                hadith_id, translation_edition_id, language, translation_text,
                translation.get("translator"), translation.get("edition_label"),
                str(translation.get("volume") or ""), str(translation.get("page") or ""),
                translation.get("rights_status") or "unverified",
                translation.get("source_url"), translation.get("notes"),
            ),
        )

    for grade in record.get("grades", []):
        original = require_text(grade.get("grade_label_original"), "grade.grade_label_original")
        normalized = (grade.get("grade_normalized") or "unknown").lower()
        if normalized not in {"sahih", "hasan", "daif", "mawdu", "unknown", "other"}:
            raise ValueError(f"Unsupported grade_normalized: {normalized}")
        grading_source = require_text(grade.get("grading_source"), "grade.grading_source")
        applies_to = (grade.get("applies_to") or "not_specified").lower()
        if applies_to not in {"narration", "specific_chain", "variant", "not_specified"}:
            applies_to = "not_specified"
        conn.execute(
            """INSERT INTO hadith_grades(
                hadith_id, grade_label_original, grade_normalized, grader_name,
                grading_source, edition_label, volume, page, reference_text,
                applies_to, notes, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                hadith_id, original, normalized, grade.get("grader_name"),
                grading_source, grade.get("edition_label"),
                str(grade.get("volume") or ""), str(grade.get("page") or ""),
                grade.get("reference_text"), applies_to, grade.get("notes"),
                grade.get("source_url"),
            ),
        )

    refresh_search_document(conn, hadith_id)
    return hadith_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Import verified hadith records from JSONL")
    parser.add_argument("input", type=Path, help="UTF-8 JSONL input file")
    parser.add_argument("--db", type=Path, default=ROOT / "hadith_records.db")
    args = parser.parse_args()
    if not args.input.is_file():
        raise SystemExit(f"Input not found: {args.input}")

    conn = connect_db(args.db)
    imported = 0
    errors = []
    with args.input.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                record = json.loads(line)
                with conn:
                    import_record(conn, record)
                imported += 1
            except Exception as exc:
                errors.append(f"Line {line_no}: {exc}")

    total = conn.execute("SELECT COUNT(*) FROM hadith_records").fetchone()[0]
    conn.close()
    print(f"Imported/updated: {imported}")
    print(f"Total hadith records in database: {total}")
    if errors:
        print("Errors:")
        for error in errors:
            print(" -", error)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
