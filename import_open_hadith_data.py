#!/usr/bin/env python3
"""Download and import Jaguar16/Open Hadith Data into the structured catalogue.

The importer preserves the source's full Arabic text, separately extracted isnad
and matn, available English text, grading labels, and source URLs. It does not
invent missing grades or narrator chains.

Usage:
    python import_open_hadith_data.py
    python import_open_hadith_data.py --archive data/source/collections-csv.zip
    python import_open_hadith_data.py --archive data/source/collections-csv.zip --db hadith_records.db
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import sqlite3
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from import_hadith_jsonl import connect_db, get_edition_id, refresh_search_document

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "source"
RELEASE_TAG = "v1.1.0"
RELEASE_API_URL = (
    "https://api.github.com/repos/Jaguar16/open-hadith-data/releases/tags/"
    f"{RELEASE_TAG}"
)
RELEASE_ASSET_NAME = "collections-csv.zip"

COLLECTION_NAMES = {
    "bukhari": ("sahih_al_bukhari", "Sahih al-Bukhari", "صحيح البخاري", "sahih"),
    "muslim": ("sahih_muslim", "Sahih Muslim", "صحيح مسلم", "sahih"),
    "nasai": ("sunan_an_nasai", "Sunan an-Nasa'i", "سنن النسائي", None),
    "abudawud": ("sunan_abi_dawud", "Sunan Abi Dawud", "سنن أبي داود", None),
    "tirmidhi": ("jami_at_tirmidhi", "Jami at-Tirmidhi", "جامع الترمذي", None),
    "ibnmajah": ("sunan_ibn_majah", "Sunan Ibn Majah", "سنن ابن ماجه", None),
    "ahmad": ("musnad_ahmad", "Musnad Ahmad", "مسند أحمد", None),
    "malik": ("muwatta_malik", "Muwatta Malik", "موطأ مالك", None),
    "darimi": ("sunan_ad_darimi", "Sunan ad-Darimi", "سنن الدارمي", None),
    "adab": ("al_adab_al_mufrad", "Al-Adab Al-Mufrad", "الأدب المفرد", None),
    "riyadussalihin": ("riyad_as_salihin", "Riyad as-Salihin", "رياض الصالحين", None),
    "bulugh": ("bulugh_al_maram", "Bulugh al-Maram", "بلوغ المرام", None),
    "shamail": ("shamail_al_muhammadiyah", "Ash-Shama'il al-Muhammadiyah", "الشمائل المحمدية", None),
    "mishkat": ("mishkat_al_masabih", "Mishkat al-Masabih", "مشكاة المصابيح", None),
    "nawawi40": ("forty_hadith_nawawi", "40 Hadith an-Nawawi", "الأربعون النووية", None),
    "qudsi40": ("forty_hadith_qudsi", "40 Hadith Qudsi", "الأربعون القدسية", None),
    "shahwaliullah40": ("forty_hadith_shah_waliullah", "Shah Waliullah's 40 Hadith", "أربعون شاه ولي الله", None),
}

def clean(value: Any) -> str:
    return str(value or "").strip()

def download_archive(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "sahih-hadith-research-app/1.0",
        "Accept": "application/vnd.github+json",
    }
    metadata_request = urllib.request.Request(RELEASE_API_URL, headers=headers)
    with urllib.request.urlopen(metadata_request, timeout=30) as response:
        release = json.loads(response.read().decode("utf-8"))
    assets = release.get("assets", [])
    asset = next((item for item in assets if item.get("name") == RELEASE_ASSET_NAME), None)
    if not asset or not asset.get("browser_download_url"):
        available = ", ".join(item.get("name", "?") for item in assets)
        raise RuntimeError(
            f"Release {RELEASE_TAG} does not expose {RELEASE_ASSET_NAME}. "
            f"Available assets: {available or 'none'}"
        )
    request = urllib.request.Request(asset["browser_download_url"], headers=headers)
    print(f"Downloading Open Hadith Data {RELEASE_TAG} ({RELEASE_ASSET_NAME})...")
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)
    if not zipfile.is_zipfile(destination):
        destination.unlink(missing_ok=True)
        raise RuntimeError("Downloaded release is not a valid ZIP archive.")
    print(f"Downloaded {destination.stat().st_size / (1024 * 1024):.1f} MiB")
    return destination

def extract_csv_archive(archive: Path, target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        for member in members:
            # Protect against path traversal in downloaded archives.
            destination = (target / member.filename).resolve()
            if target.resolve() not in destination.parents and destination != target.resolve():
                raise RuntimeError(f"Unsafe path in archive: {member.filename}")
        zf.extractall(target)
    matches = list(target.rglob("hadiths.csv"))
    if not matches:
        raise FileNotFoundError("Release archive does not contain hadiths.csv")
    return matches[0]

def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def normalize_grade(source_grade: str, grade_en: str, grade_ar: str) -> str:
    label = clean(grade_en).lower()
    arabic = clean(grade_ar)
    # Compound or qualified labels remain "other": do not flatten a nuanced
    # scholarly expression into a single grade category.
    if "hasan sahih" in label or "sahih hasan" in label or ("صحيح" in arabic and "حسن" in arabic):
        return "other"
    raw = clean(source_grade).lower()
    if raw in {"sahih", "hasan", "daif", "mawdu"}:
        return raw
    if re.match(r"^sahih(?:\s|$|\()", label):
        return "sahih"
    if re.match(r"^hasan(?:\s|$|\()", label):
        return "hasan"
    if re.match(r"^(da['’]?if|daeef|weak)(?:\s|$|\()", label):
        return "daif"
    if re.match(r"^(mawdu['’]?|fabricated)(?:\s|$|\()", label):
        return "mawdu"
    arabic = clean(grade_ar)
    if "صحيح" in arabic and "حسن" not in arabic:
        return "sahih"
    if "حسن" in arabic and "صحيح" not in arabic:
        return "hasan"
    if "ضعيف" in arabic:
        return "daif"
    if "موضوع" in arabic:
        return "mawdu"
    return "other" if (label or arabic) else "unknown"

def load_lookup_rows(csv_path: Path | None) -> dict[tuple[str, str], str]:
    if not csv_path or not csv_path.exists():
        return {}
    rows = read_csv_rows(csv_path)
    output: dict[tuple[str, str], str] = {}
    for row in rows:
        collection = clean(row.get("collection_id"))
        number = clean(row.get("book_number"))
        book_key = clean(row.get("book_key"))
        name = clean(row.get("name_en"))
        if collection and name:
            if number:
                output[(collection, number)] = name
            if book_key:
                output[(collection, book_key)] = name
    return output

def load_chapter_lookup(csv_path: Path | None) -> dict[tuple[str, str, str], str]:
    if not csv_path or not csv_path.exists():
        return {}
    output: dict[tuple[str, str, str], str] = {}
    for row in read_csv_rows(csv_path):
        key = (clean(row.get("collection_id")), clean(row.get("book_number")), clean(row.get("chapter_number")))
        if all(key):
            output[key] = clean(row.get("name_en"))
    return output

def import_source_rows(rows: list[dict[str, str]], db_path: Path,
                       books: dict[tuple[str, str], str] | None = None,
                       chapters: dict[tuple[str, str, str], str] | None = None) -> dict[str, Any]:
    books = books or {}
    chapters = chapters or {}
    conn = connect_db(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    imported = 0
    skipped = 0
    errors: list[str] = []
    seen_keys: set[str] = set()

    for line_no, row in enumerate(rows, start=2):
        source_collection = clean(row.get("collection_id")).lower()
        if source_collection not in COLLECTION_NAMES:
            skipped += 1
            continue
        slug, name_en, name_ar, collection_grade = COLLECTION_NAMES[source_collection]
        number = clean(row.get("hadith_number"))
        text_ar = clean(row.get("text_ar"))
        if not number or not text_ar:
            skipped += 1
            continue
        url = clean(row.get("url_source"))
        key_suffix = url or clean(row.get("reference")) or f"row-{line_no}"
        hadith_key = f"open-hadith-data:{source_collection}:{number}:{key_suffix}"
        if hadith_key in seen_keys:
            hadith_key += f":row-{line_no}"
        seen_keys.add(hadith_key)

        try:
            with conn:
                conn.execute(
                    """INSERT OR IGNORE INTO collections(
                        collection_slug, collection_name_en, collection_name_ar,
                        collection_grade_label, collection_grade_basis
                    ) VALUES (?, ?, ?, ?, ?)""",
                    (slug, name_en, name_ar, collection_grade,
                     "Collection-level designation only; not an individual chain grade."
                     if collection_grade else None),
                )
                collection_id = conn.execute(
                    "SELECT id FROM collections WHERE collection_slug=?", (slug,)
                ).fetchone()[0]

                edition_ar = {
                    "edition_slug": f"open-hadith-data-{RELEASE_TAG}-ar",
                    "edition_label": f"Open Hadith Data {RELEASE_TAG}; Arabic text extracted from Sunnah.com",
                    "language": "ar",
                    "rights_status": "structured-data-cc0; verify source text rights",
                    "notes": "Automatically extracted dataset. Verify against a printed critical edition before scholarly use.",
                }
                edition_en = {
                    "edition_slug": f"open-hadith-data-{RELEASE_TAG}-en",
                    "edition_label": f"Open Hadith Data {RELEASE_TAG}; English text sourced from Sunnah.com",
                    "language": "en",
                    "rights_status": "review-sunnah-com-translation-redistribution-terms",
                    "notes": "Translator attribution is not exposed in the source CSV. Review redistribution rights before public hosting.",
                }
                # Import edition metadata using the same rules as the main importer.
                edition_ar_id = get_edition_id(conn, collection_id, edition_ar)
                edition_en_id = get_edition_id(conn, collection_id, edition_en)

                book_number = clean(row.get("book_number"))
                chapter_number = clean(row.get("chapter_number"))
                book_title = books.get((source_collection, book_number), "")
                chapter_title = chapters.get((source_collection, book_number, chapter_number), "")
                conn.execute(
                    """INSERT INTO hadith_records(
                        hadith_key, collection_id, edition_id, hadith_number,
                        book_number, book_title, chapter_number, chapter_title,
                        arabic_full, isnad_ar, matn_ar, source_reference, source_url,
                        transcription_status, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unverified', ?)""",
                    (
                        hadith_key, collection_id, edition_ar_id, number,
                        book_number or None, book_title or None,
                        chapter_number or None, chapter_title or None,
                        text_ar, clean(row.get("isnad_ar")) or None,
                        clean(row.get("matn_ar")) or None,
                        clean(row.get("source_reference")) or None, url or None,
                        json.dumps({
                            "source_dataset": "Jaguar16/open-hadith-data",
                            "source_version": RELEASE_TAG,
                            "source_collection_id": source_collection,
                            "reference": clean(row.get("reference")),
                            "in_book_reference": clean(row.get("in_book_reference")),
                            "isnad_en": clean(row.get("isnad_en")),
                            "matn_en": clean(row.get("matn_en")),
                            "closing_ar": clean(row.get("closing_ar")),
                            "narrator": clean(row.get("narrator")),
                            "has_variants": clean(row.get("has_variants")),
                            "source_reference": clean(row.get("source_reference")),
                            "source_grade": clean(row.get("source_grade")),
                            "grade_ar": clean(row.get("grade_ar")),
                        }, ensure_ascii=False),
                    ),
                )
                hadith_id = conn.execute(
                    "SELECT id FROM hadith_records WHERE hadith_key=?", (hadith_key,)
                ).fetchone()[0]
                # Keep imports idempotent when the same pinned source release
                # is imported again.
                conn.execute("DELETE FROM hadith_translations WHERE hadith_id=?", (hadith_id,))
                conn.execute("DELETE FROM hadith_grades WHERE hadith_id=?", (hadith_id,))

                text_en = clean(row.get("text_en"))
                if text_en:
                    conn.execute(
                        """INSERT INTO hadith_translations(
                            hadith_id, edition_id, language, translation_text,
                            translator, edition_label, rights_status, source_url, notes
                        ) VALUES (?, ?, 'en', ?, NULL, ?, ?, ?, ?)""",
                        (
                            hadith_id, edition_en_id, text_en,
                            edition_en["edition_label"], edition_en["rights_status"],
                            url or None,
                            "Full English text from source export; translator not identified in CSV.",
                        ),
                    )

                grade_en = clean(row.get("grade_en"))
                grade_ar = clean(row.get("grade_ar"))
                source_grade = clean(row.get("source_grade"))
                grade_label = grade_en or grade_ar
                if grade_label:
                    normalized = normalize_grade(source_grade, grade_en, grade_ar)
                    conn.execute(
                        """INSERT INTO hadith_grades(
                            hadith_id, grade_label_original, grade_normalized,
                            grader_name, grading_source, edition_label,
                            reference_text, applies_to, notes, source_url
                        ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'not_specified', ?, ?)""",
                        (
                            hadith_id, grade_label, normalized,
                            "Sunnah.com grade field as extracted by Open Hadith Data",
                            f"Open Hadith Data {RELEASE_TAG}",
                            clean(row.get("reference")) or None,
                            f"Arabic grade label: {grade_ar or 'not supplied'}; "
                            "the source export does not identify whether the grade applies to a particular chain or a narration variant.",
                            url or None,
                        ),
                    )

                refresh_search_document(conn, int(hadith_id))
            imported += 1
        except Exception as exc:
            errors.append(f"CSV row {line_no} ({source_collection}:{number}): {exc}")

    total = conn.execute("SELECT COUNT(*) FROM hadith_records").fetchone()[0]
    per_collection = conn.execute(
        """SELECT c.collection_slug, c.collection_name_en, COUNT(h.id)
           FROM collections c JOIN hadith_records h ON h.collection_id=c.id
           GROUP BY c.id ORDER BY c.collection_name_en"""
    ).fetchall()
    conn.close()
    return {
        "imported_or_updated": imported,
        "skipped": skipped,
        "total_records": int(total),
        "collections": [{"slug": r[0], "name": r[1], "records": int(r[2])} for r in per_collection],
        "errors": errors,
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Import structured hadiths from Open Hadith Data.")
    parser.add_argument("--archive", type=Path, default=None, help="Existing collections-csv.zip; downloads release if omitted.")
    parser.add_argument("--db", type=Path, default=ROOT / "hadith_records.db")
    args = parser.parse_args()

    archive = args.archive or DATA_DIR / f"collections-csv-{RELEASE_TAG}.zip"
    if not archive.exists():
        download_archive(archive)
    extracted_dir = DATA_DIR / f"open-hadith-data-{RELEASE_TAG}"
    hadith_csv = extract_csv_archive(archive, extracted_dir)
    books_csv = next(iter(extracted_dir.rglob("books.csv")), None)
    chapters_csv = next(iter(extracted_dir.rglob("chapters.csv")), None)

    args.db.parent.mkdir(parents=True, exist_ok=True)
    result = import_source_rows(
        read_csv_rows(hadith_csv),
        args.db,
        load_lookup_rows(books_csv),
        load_chapter_lookup(chapters_csv),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["errors"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
