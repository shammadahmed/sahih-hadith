PRAGMA foreign_keys = ON;

-- Reviewed relationships only. Group membership never merges source records,
-- numbering, matn variants, chains, translations or grades.
CREATE TABLE IF NOT EXISTS narration_groups (
    id INTEGER PRIMARY KEY,
    group_key TEXT NOT NULL UNIQUE,
    label TEXT,
    relationship_summary TEXT,
    review_status TEXT NOT NULL DEFAULT 'proposed'
      CHECK(review_status IN ('proposed','reviewed','rejected')),
    reviewer TEXT,
    reviewed_at TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS narration_group_members (
    group_id INTEGER NOT NULL REFERENCES narration_groups(id) ON DELETE CASCADE,
    hadith_id INTEGER NOT NULL REFERENCES hadith_records(id) ON DELETE CASCADE,
    member_note TEXT,
    PRIMARY KEY(group_id, hadith_id)
);
CREATE TABLE IF NOT EXISTS hadith_chains (
    id INTEGER PRIMARY KEY,
    hadith_id INTEGER NOT NULL REFERENCES hadith_records(id) ON DELETE CASCADE,
    chain_text_ar TEXT NOT NULL,
    chain_text_transliteration TEXT,
    source_reference TEXT,
    source_url TEXT,
    transcription_status TEXT NOT NULL DEFAULT 'unverified'
      CHECK(transcription_status IN ('unverified','reviewed','verified')),
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_hadith_chains_hadith ON hadith_chains(hadith_id);
CREATE TABLE IF NOT EXISTS hadith_cross_references (
    id INTEGER PRIMARY KEY,
    from_hadith_id INTEGER NOT NULL REFERENCES hadith_records(id) ON DELETE CASCADE,
    to_hadith_id INTEGER NOT NULL REFERENCES hadith_records(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL CHECK(relation_type IN (
      'parallel_narration','same_event_variant','shared_companion',
      'same_matn_variant','thematic_parallel','other'
    )),
    confidence TEXT NOT NULL DEFAULT 'unreviewed'
      CHECK(confidence IN ('unreviewed','low','medium','high')),
    review_status TEXT NOT NULL DEFAULT 'proposed'
      CHECK(review_status IN ('proposed','reviewed','rejected')),
    evidence_note TEXT,
    reviewer TEXT,
    source_reference TEXT,
    CHECK(from_hadith_id <> to_hadith_id),
    UNIQUE(from_hadith_id,to_hadith_id,relation_type)
);
CREATE INDEX IF NOT EXISTS idx_hadith_cross_from ON hadith_cross_references(from_hadith_id);
CREATE INDEX IF NOT EXISTS idx_hadith_cross_to ON hadith_cross_references(to_hadith_id);
