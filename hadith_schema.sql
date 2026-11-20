PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY,
    collection_slug TEXT NOT NULL UNIQUE,
    collection_name_en TEXT NOT NULL,
    collection_name_ar TEXT,
    tradition TEXT NOT NULL DEFAULT 'Sunni',
    collection_grade_label TEXT CHECK(collection_grade_label IN ('sahih','hasan','daif','mawdu','other') OR collection_grade_label IS NULL),
    collection_grade_basis TEXT
);

CREATE TABLE IF NOT EXISTS editions (
    id INTEGER PRIMARY KEY,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    edition_slug TEXT NOT NULL,
    edition_label TEXT NOT NULL,
    language TEXT NOT NULL CHECK(language IN ('ar','ur','en','other')),
    translator TEXT,
    editor TEXT,
    researcher TEXT,
    publisher TEXT,
    publication_year TEXT,
    archive_identifier TEXT,
    source_url TEXT,
    rights_status TEXT NOT NULL DEFAULT 'unverified',
    notes TEXT,
    UNIQUE(collection_id, edition_slug, language)
);

-- One row represents one narration as represented in a particular collection
-- and edition. Do not merge variants or edition-specific numbering automatically.
CREATE TABLE IF NOT EXISTS hadith_records (
    id INTEGER PRIMARY KEY,
    hadith_key TEXT NOT NULL UNIQUE,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    edition_id INTEGER REFERENCES editions(id),
    hadith_number TEXT NOT NULL,
    book_number TEXT,
    book_title TEXT,
    chapter_number TEXT,
    chapter_title TEXT,
    arabic_full TEXT,
    isnad_ar TEXT,
    matn_ar TEXT,
    source_volume TEXT,
    source_page_start TEXT,
    source_page_end TEXT,
    source_reference TEXT,
    source_url TEXT,
    transcription_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK(transcription_status IN ('unverified','reviewed','verified')),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_hadith_collection_number
    ON hadith_records(collection_id, hadith_number);
CREATE INDEX IF NOT EXISTS idx_hadith_edition
    ON hadith_records(edition_id);

CREATE TABLE IF NOT EXISTS hadith_translations (
    id INTEGER PRIMARY KEY,
    hadith_id INTEGER NOT NULL REFERENCES hadith_records(id) ON DELETE CASCADE,
    edition_id INTEGER REFERENCES editions(id),
    language TEXT NOT NULL CHECK(language IN ('ur','en','ar','other')),
    translation_text TEXT NOT NULL,
    translator TEXT,
    edition_label TEXT,
    volume TEXT,
    page TEXT,
    rights_status TEXT NOT NULL DEFAULT 'unverified',
    source_url TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_hadith_translations_lookup
    ON hadith_translations(hadith_id, language);

-- Grades are observations with provenance, not a single property of a hadith.
-- One narration may have multiple scholarly assessments or chain-specific grades.
CREATE TABLE IF NOT EXISTS hadith_grades (
    id INTEGER PRIMARY KEY,
    hadith_id INTEGER NOT NULL REFERENCES hadith_records(id) ON DELETE CASCADE,
    grade_label_original TEXT NOT NULL,
    grade_normalized TEXT NOT NULL DEFAULT 'unknown'
        CHECK(grade_normalized IN ('sahih','hasan','daif','mawdu','unknown','other')),
    grader_name TEXT,
    grading_source TEXT NOT NULL,
    edition_label TEXT,
    volume TEXT,
    page TEXT,
    reference_text TEXT,
    applies_to TEXT NOT NULL DEFAULT 'narration'
        CHECK(applies_to IN ('narration','specific_chain','variant','not_specified')),
    notes TEXT,
    source_url TEXT
);
CREATE INDEX IF NOT EXISTS idx_hadith_grades_lookup
    ON hadith_grades(grade_normalized, hadith_id);

-- Denormalized search document. Canonical text remains in the tables above.
CREATE TABLE IF NOT EXISTS hadith_search_documents (
    hadith_id INTEGER PRIMARY KEY REFERENCES hadith_records(id) ON DELETE CASCADE,
    collection_text TEXT NOT NULL DEFAULT '',
    hadith_number TEXT NOT NULL DEFAULT '',
    book_title TEXT NOT NULL DEFAULT '',
    chapter_title TEXT NOT NULL DEFAULT '',
    arabic_full TEXT NOT NULL DEFAULT '',
    isnad_ar TEXT NOT NULL DEFAULT '',
    matn_ar TEXT NOT NULL DEFAULT '',
    translation_text TEXT NOT NULL DEFAULT '',
    grade_text TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS hadith_fts USING fts5(
    collection_text,
    hadith_number,
    book_title,
    chapter_title,
    arabic_full,
    isnad_ar,
    matn_ar,
    translation_text,
    grade_text,
    content='hadith_search_documents',
    content_rowid='hadith_id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS hadith_search_ai AFTER INSERT ON hadith_search_documents BEGIN
    INSERT INTO hadith_fts(rowid, collection_text, hadith_number, book_title,
        chapter_title, arabic_full, isnad_ar, matn_ar, translation_text, grade_text)
    VALUES (new.hadith_id, new.collection_text, new.hadith_number, new.book_title,
        new.chapter_title, new.arabic_full, new.isnad_ar, new.matn_ar,
        new.translation_text, new.grade_text);
END;

CREATE TRIGGER IF NOT EXISTS hadith_search_ad AFTER DELETE ON hadith_search_documents BEGIN
    INSERT INTO hadith_fts(hadith_fts, rowid, collection_text, hadith_number,
        book_title, chapter_title, arabic_full, isnad_ar, matn_ar,
        translation_text, grade_text)
    VALUES ('delete', old.hadith_id, old.collection_text, old.hadith_number,
        old.book_title, old.chapter_title, old.arabic_full, old.isnad_ar,
        old.matn_ar, old.translation_text, old.grade_text);
END;

CREATE TRIGGER IF NOT EXISTS hadith_search_au AFTER UPDATE ON hadith_search_documents BEGIN
    INSERT INTO hadith_fts(hadith_fts, rowid, collection_text, hadith_number,
        book_title, chapter_title, arabic_full, isnad_ar, matn_ar,
        translation_text, grade_text)
    VALUES ('delete', old.hadith_id, old.collection_text, old.hadith_number,
        old.book_title, old.chapter_title, old.arabic_full, old.isnad_ar,
        old.matn_ar, old.translation_text, old.grade_text);
    INSERT INTO hadith_fts(rowid, collection_text, hadith_number, book_title,
        chapter_title, arabic_full, isnad_ar, matn_ar, translation_text, grade_text)
    VALUES (new.hadith_id, new.collection_text, new.hadith_number, new.book_title,
        new.chapter_title, new.arabic_full, new.isnad_ar, new.matn_ar,
        new.translation_text, new.grade_text);
END;

INSERT OR IGNORE INTO collections(collection_slug, collection_name_en, collection_name_ar, collection_grade_label, collection_grade_basis) VALUES
('sahih_al_bukhari', 'Sahih al-Bukhari', 'صحيح البخاري', 'sahih', 'Collection designation; not a separate grading of each narration or chain.'),
('sahih_muslim', 'Sahih Muslim', 'صحيح مسلم', 'sahih', 'Collection designation; not a separate grading of each narration or chain.'),
('sunan_abi_dawud', 'Sunan Abi Dawud', 'سنن أبي داود', NULL, NULL),
('jami_at_tirmidhi', 'Jami at-Tirmidhi', 'جامع الترمذي', NULL, NULL),
('sunan_an_nasai', 'Sunan an-Nasa’i', 'سنن النسائي', NULL, NULL),
('sunan_ibn_majah', 'Sunan Ibn Majah', 'سنن ابن ماجه', NULL, NULL),
('musnad_ahmad', 'Musnad Imam Ahmad', 'مسند الإمام أحمد', NULL, NULL);
