import sqlite3
import tempfile
import unittest
from pathlib import Path

from import_open_hadith_data import import_source_rows
from import_hadith_jsonl import connect_db


class OpenHadithImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "hadith_records.db"

    def tearDown(self):
        self.temp.cleanup()

    def sample(self):
        return [{
            "collection_id": "tirmidhi",
            "book_number": "1",
            "chapter_number": "1",
            "hadith_number": "1",
            "reference": "Jami at-Tirmidhi 1",
            "in_book_reference": "Book 1, Hadith 1",
            "text_ar": "حَدَّثَنَا قُتَيْبَةُ عَنْ مَالِكٍ قَالَ رَسُولُ اللَّهِ",
            "text_en": "Narrated Abu Hurairah: The Messenger of Allah said...",
            "isnad_ar": "حَدَّثَنَا قُتَيْبَةُ عَنْ مَالِكٍ",
            "isnad_en": "Narrated Abu Hurairah",
            "matn_ar": "قَالَ رَسُولُ اللَّهِ",
            "matn_en": "The Messenger of Allah said...",
            "closing_ar": "",
            "narrator": "Abu Hurairah",
            "has_variants": "false",
            "source_reference": "",
            "source_grade": "sahih",
            "grade_en": "Sahih (Darussalam)",
            "grade_ar": "صحيح (دار السلام)",
            "url_source": "https://sunnah.com/tirmidhi:1",
        }]

    def test_import_preserves_chain_matn_translation_grade_and_source(self):
        result = import_source_rows(
            self.sample(), self.db,
            {("tirmidhi", "1"): "The Book on Purification"},
            {("tirmidhi", "1", "1"): "Chapter: Purification"},
        )
        self.assertEqual(result["imported_or_updated"], 1)
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        record = conn.execute("SELECT * FROM hadith_records").fetchone()
        self.assertEqual(record["isnad_ar"], "حَدَّثَنَا قُتَيْبَةُ عَنْ مَالِكٍ")
        self.assertEqual(record["matn_ar"], "قَالَ رَسُولُ اللَّهِ")
        self.assertIn("حَدَّثَنَا", record["arabic_full"])
        self.assertEqual(record["book_title"], "The Book on Purification")
        self.assertEqual(record["chapter_title"], "Chapter: Purification")
        translation = conn.execute("SELECT * FROM hadith_translations").fetchone()
        self.assertIn("Messenger of Allah", translation["translation_text"])
        grade = conn.execute("SELECT * FROM hadith_grades").fetchone()
        self.assertEqual(grade["grade_normalized"], "sahih")
        self.assertEqual(grade["applies_to"], "not_specified")
        self.assertEqual(grade["source_url"], "https://sunnah.com/tirmidhi:1")
        conn.close()

    def test_import_is_idempotent(self):
        import_source_rows(self.sample(), self.db)
        result = import_source_rows(self.sample(), self.db)
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM hadith_records").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM hadith_translations").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM hadith_grades").fetchone()[0], 1)
        conn.close()
        self.assertEqual(result["total_records"], 1)

    def test_compound_grade_is_not_flattened(self):
        from import_open_hadith_data import normalize_grade
        self.assertEqual(
            normalize_grade("", "Hasan Sahih (Al-Albani)", "حسن صحيح"),
            "other",
        )


if __name__ == "__main__":
    unittest.main()
