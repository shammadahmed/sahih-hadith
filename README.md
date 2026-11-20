# Sunni Hadith Research RAG

A Streamlit hadith research app that combines a structured, multi-collection individual-hadith catalogue, the legacy Sahih al-Bukhari passage index, session-scoped user uploads, and exhaustive lexical search.

## Multi-collection structured corpus (new)

The app can import the pinned **[Jaguar16/Open Hadith Data v1.1.0](https://github.com/Jaguar16/open-hadith-data/tree/v1.1.0)**
release into `hadith_records.db`. The source project reports 46,891 hadith
records across 17 hadith collections and provides individual-record fields
including full Arabic text, separately extracted `isnad_ar` and `matn_ar`,
English text, grade labels, and direct source URLs. Its [data license and
translation caveats](https://github.com/Jaguar16/open-hadith-data/blob/v1.1.0/DATA_LICENSE.md)
are recorded below.

Run this once from the project directory:

```bash
python import_open_hadith_data.py
```

The script downloads the pinned `collections-csv.zip` release, extracts it under
`data/source/`, and imports its individual records into `hadith_records.db`.
To use an archive you already downloaded:

```bash
python import_open_hadith_data.py --archive path/to/collections-csv.zip
```

To import into a custom database:

```bash
python import_open_hadith_data.py --db hadith_records.db
```

The Streamlit app automatically detects `hadith_records.db`. Both **Ask with RAG**
and **Find all matching hadiths** can then search the selected imported collections.
The legacy 4,488-passage Bukhari index becomes an optional supplementary source.

For Streamlit Community Cloud, run the importer locally first, then deploy the
generated `hadith_records.db` beside `app.py` with the repository. Check the
database file size before committing; if it exceeds GitHub's 100 MB per-file
limit, store it in an external object store and adapt the deployment to fetch
that pinned database artifact. Do not run the full import on every app rerun.

### Data provenance and important limits

- The source dataset says it was automatically extracted from Sunnah.com. Its
  maintainers explicitly warn that the extraction may contain errors and is not
  guaranteed complete or correct. Verify scholarly use against authenticated
  printed editions and qualified scholarship.
- The source README lists 1,374 Musnad Ahmad records in this snapshot. This is
  **not evidence that the full Musnad Ahmad has been imported**.
- The source documentation says that for some variant narrations only the first
  variant is retained and `has_variants` is set. This release therefore cannot
  claim exhaustive variant coverage.
- Some collections have no English text or no grade field. Missing grades remain
  missing; the importer never invents a grade.
- Grade labels are preserved verbatim. The normalized grade filter only maps
  clear, unambiguous labels. Compound labels such as "Hasan Sahih" remain
  `other`, rather than being silently reduced to one grade.
- The export does not identify the grader separately for every grade label or
  state whether a grade applies to a particular chain or variant. The app marks
  the scope as `not_specified` and records the source page. It does not invent a
  named scholar.
- The structured-data organization is stated by its maintainers to be CC0.
  English translations are sourced from Sunnah.com and may have separate
  redistribution restrictions. The importer records this warning in edition
  metadata; review Sunnah.com's terms before publicly redistributing those
  translations.
- The importer preserves full Arabic text, `isnad_ar`, and `matn_ar` as
  separate fields when present. The UI displays the source's full Arabic text
  alongside the separate chain and matn fields.

This is a useful broad research corpus, not a scholarly critical edition or a
guarantee that every narration, chain variant, or grading opinion is present.

## What is implemented in this release

### 1. Existing preloaded corpus

- Nine-volume Sahih al-Bukhari English/Arabic-derived passage index.
- 4,488 multi-hadith passages in `bukhari_fts.db`.
- The bundled index is read-only and ready when the app starts. The app does not parse EPUBs or rebuild this corpus at startup.
- Existing retrieval uses SQLite FTS5/BM25 with configured lexical term expansions.

**Important data limitation:** the supplied Bukhari index contains multi-hadith passages, not a verified one-row-per-hadith catalogue. It does not have separate canonical Arabic full text, isnad, matn, Urdu translation, English translation, or per-hadith grading rows. Do not treat these OCR-derived passage results as a verified list of individual narrations or as grading evidence.

### 2. Two query modes

- **Ask with RAG:** retrieve individual structured hadith records from the imported multi-collection catalogue, then ask Groq to formulate a source-grounded answer. The legacy Bukhari passages and user uploads are optional supplements.
- **Find all matching hadiths:** return every FTS5 lexical candidate from the selected structured catalogue and supplementary sources, with pagination and JSON export. This mode does not require a Groq API key. Choose “Any query term” for broader recall or “All query terms” for a narrower result set.

The term “all” means all lexical matches returned by the FTS index for the selected query and imported corpus. It does **not** guarantee semantic recall for paraphrases, transliterations, spelling variants, or concepts that share no searchable words. The structured importer targets 17 collections in the pinned source snapshot; actual coverage is whatever records the source release supplies and that you successfully import.

### 3. User uploads

- Supported: TXT, MD, CSV, text-based PDF, DOCX.
- Uploads are indexed only after the user clicks **Add files to this chat**.
- Passages are stored in a session-scoped in-memory SQLite FTS5 index. They do not modify the bundled Bukhari index.
- Scanned/image-only PDFs need OCR before upload.

### 4. Optional structured hadith catalogue

The app searches and displays individual hadith records when `hadith_records.db` is present next to `app.py`. The pinned source importer supplies full Arabic text, separate isnad/matn where present, English text, available grade labels and source URLs. Urdu translations can be added separately using the JSONL importer. Collection and grade filters are supported.

The database schema is in `hadith_schema.sql`. It stores:

- `hadith_records`: edition-aware narration record and source reference.
- `hadith_translations`: separate translation records with translator, edition, language and rights status.
- `hadith_grades`: multiple independent assessments per narration, including original grade wording, normalized grade, grader, grading source, reference and chain scope.
- `hadith_search_documents` / `hadith_fts`: multilingual search text.

A grade belongs to an attributed grading observation, not to an unqualified `grade` property on the narration. Different scholars may grade the same narration or chain differently. The app must not infer individual grades from wording. It may include records from Sahih al-Bukhari and Sahih Muslim in a Sahih filter by their collection designation, but it labels that basis separately from an individually attributed chain/narration grade.

#### Import reviewed JSONL records

Create a UTF-8 JSONL file with one edition-specific narration per line, then run:

```bash
python import_hadith_jsonl.py path/to/verified_hadith_records.jsonl --db hadith_records.db
```

The importer is idempotent by `hadith_key`. It does not generate Arabic, translate text, split isnad/matn, infer grades, correct numbering, or verify source licensing. Those must be supplied and reviewed before import.

Minimum record shape:

```json
{
  "hadith_key": "sahih_al_bukhari:edition_slug:hadith_1",
  "collection_slug": "sahih_al_bukhari",
  "collection_name_en": "Sahih al-Bukhari",
  "collection_name_ar": "صحيح البخاري",
  "hadith_number": "1",
  "edition": {
    "edition_slug": "arabic_edition_slug",
    "edition_label": "Full bibliographic edition description",
    "language": "ar",
    "publisher": "Publisher",
    "rights_status": "verify-before-redistribution"
  },
  "book_title": "Book of Revelation",
  "chapter_title": "How the Divine Revelation started",
  "arabic_full": "Exact Arabic text copied from the identified edition",
  "isnad_ar": "Exact chain text, if separately verified",
  "matn_ar": "Exact matn text, if separately verified",
  "transcription_status": "reviewed",
  "source": {
    "volume": "1",
    "page_start": "1",
    "page_end": "2",
    "reference": "Edition-specific reference",
    "url": "https://example.org/source"
  },
  "translations": [
    {
      "language": "ur",
      "translation_text": "Exact published Urdu translation",
      "translator": "Translator name",
      "edition_label": "Urdu edition description",
      "volume": "1",
      "page": "1",
      "rights_status": "permission-required"
    },
    {
      "language": "en",
      "translation_text": "Exact published English translation",
      "translator": "Translator name",
      "edition_label": "English edition description",
      "volume": "1",
      "page": "1",
      "rights_status": "permission-required"
    }
  ],
  "grades": [
    {
      "grade_label_original": "Exact grading expression as printed",
      "grade_normalized": "sahih",
      "grader_name": "Named scholar",
      "grading_source": "Named takhrij / tahqiq work",
      "edition_label": "Grading source edition",
      "volume": "1",
      "page": "10",
      "reference_text": "Exact reference or locator",
      "applies_to": "specific_chain",
      "notes": "Optional scholarly note"
    }
  ]
}
```

Only include `grades` when an identifiable source explicitly makes the assessment. Valid normalized values: `sahih`, `hasan`, `daif`, `mawdu`, `unknown`, `other`. Preserve the original Arabic/Urdu grading phrase in `grade_label_original`.

For a translation from a separate edition, include an `edition` object inside that translation with its own `edition_slug`, `edition_label`, `language`, translator and bibliographic details. Do not silently attach a translation to the Arabic edition.

## Exhaustive search behavior

The **Find all matching hadiths** mode:

1. Searches all matching FTS5 candidate passages in each selected passage index (no top-k truncation).
2. Combines multiple result lists using reciprocal-rank fusion.
3. Displays all candidates in pages of 20 and allows JSON export of the complete result list.
4. Searches `hadith_records.db` separately when it contains structured records, returning individual narration cards and applying selected collection/grade filters.
5. Never applies an individual grade filter to legacy passages or uploaded documents without grade provenance.

For broad queries, use “Any query term” and review more candidates. Use “All query terms” to narrow results. A keyword index cannot guarantee all conceptually relevant narrations. A future hybrid retriever should add Arabic/Urdu-aware dense retrieval, query expansion and reranking, then validate recall against a human-reviewed evaluation set.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Set the Groq key using Streamlit secrets:

```toml
Groq_key = "your_groq_api_key_here"
```

Or set `GROQ_API_KEY` as an environment variable. Groq is only required for **Ask with RAG**; exhaustive lexical search works without it.

## Deploy to Streamlit Community Cloud

1. Push `app.py`, `requirements.txt`, `bukhari_fts.db`, `index_manifest.json`, `hadith_schema.sql`, `import_hadith_jsonl.py`, and `import_open_hadith_data.py` to your GitHub repository.
2. Run `python import_open_hadith_data.py` locally to create `hadith_records.db`, then deploy that database beside `app.py`. Check the file size and translation redistribution terms before committing it. If it is too large for GitHub, use external object storage and fetch a pinned artifact at deployment.
3. Create the Streamlit app with `app.py` as entry point.
4. Add `Groq_key` in Streamlit app Settings → Secrets for generated answers.

Do not commit a real API key. Uploaded text is sent to Groq only when used as answer context in **Ask with RAG**. Search-only mode runs locally on the app host.

## Source quality and rights

- Preserve source editions, numbering, page references and original text.
- Keep Arabic full text intact. Do not use AI to reconstruct OCR-corrupted Arabic or missing isnad.
- Record translations with translator and edition attribution.
- Record grading as multiple attributed assessments. Never assign a grade automatically from the collection label or model judgement.
- Do not redistribute Internet Archive translations or extracted book text unless the relevant rights permit it. Store and review rights status per edition and translation.

## Current scope

The repository now includes an importer for the pinned Open Hadith Data v1.1.0 snapshot. The data itself is not bundled in this code ZIP: run the importer to download and create the local catalogue. The source reports 46,891 records across 17 collections, but its Musnad Ahmad subset is 1,374 records, some variant narrations are not separate rows, and the maintainers disclaim completeness and correctness. This is not a complete seven-book critical corpus. Review the source data and translations before scholarly use or public redistribution.

## Example: find all matching Sahih hadith

1. Choose **Find all matching hadiths** in the sidebar.
2. Enable **Search structured hadith records across collections** when a populated `hadith_records.db` is installed.
3. Select one or more collections and choose the requested grade, or let the app detect an explicit grade term in the question.
4. Ask a question such as:

   ```text
   Give me all Sahih hadith about intentions.
   ```

5. The results show individual records when the structured catalogue is present. Each record can display its original Arabic text, separately supplied isnad and matn, Urdu/English translations with translator/edition attribution, and all imported grading observations.
6. Download the complete matched record set as JSON. The UI paginates the results but the export contains the complete result set.

Without `hadith_records.db`, the app can only return passage candidates from the preloaded Bukhari index and uploaded documents. It explicitly warns that those candidates have not been individually graded and cannot be presented as a verified all-Sahih list.

### Prepare the structured catalogue

The seven principal collection identities are pre-seeded in `hadith_schema.sql`. The recommended first import is the pinned multi-collection source pipeline above. For additional individually reviewed records, create a UTF-8 JSONL file (one edition-specific narration per line) and run:

```bash
python import_hadith_jsonl.py verified_hadith_records.jsonl --db hadith_records.db
```

Place the resulting `hadith_records.db` beside `app.py` and restart the app. Use edition-specific `hadith_key` values; do not merge different numbering systems or variants merely because their printed numbers match.

For manual additions, provide explicit source text, edition metadata and provenance for every translation and grade. The pinned source export may not identify a named grader or chain-specific scope for every grade; those fields remain explicitly unrecorded rather than being inferred. Set `transcription_status` to `verified` only after checking the original edition.

### Search limitations to understand

- `Find all matching hadiths` currently performs exhaustive **lexical** search over the selected local FTS indexes. The phrase “all matching” does not mean guaranteed semantic recall.
- Query expansions are a lightweight recall aid, not a scholarly synonym model or a substitute for Arabic/Urdu-aware dense retrieval.
- The legacy Bukhari index has OCR damage and passage-level segmentation; search results from it are candidates, not individual canonical hadith records.
- Grade filtering is applied only to structured records with grading provenance (plus separately labelled collection-level Sahih designation for Bukhari/Muslim). User-uploaded documents and legacy passages are never silently treated as individually graded hadiths.
- For a rigorous “all relevant narrations” claim, build a human-reviewed query/evidence evaluation set and measure recall before describing the search as exhaustive in a semantic sense.


## Domain restriction (Islam and hadith only)

The app includes a fail-closed domain gate in `domain_guard.py`:

- Every user question is checked **before retrieval** in both RAG and exhaustive-search modes.
- In RAG mode, the Groq model classifies ambiguous questions against a strict Islamic-studies scope. The classifier is instructed to judge the user's actual intent, not merely detect a keyword, and to ignore prompt-injection attempts.
- Without a Groq key, a deterministic vocabulary gate allows clear Islamic questions and rejects unrelated or ambiguous ones. This is intentionally conservative.
- The answer system prompt independently prohibits answering unrelated questions, even if retrieved passages contain coincidental matches.
- Out-of-scope questions receive a short refusal and are not sent to corpus retrieval.

Supported scope includes Quran, Sunnah, hadith, hadith sciences, Islamic belief, worship, fiqh, Islamic history and related Muslim scholarship. The domain gate is a practical safeguard, not a perfect semantic classifier; review ambiguous cases and keep the classifier prompt/tests updated.

## Cross-collection relationships

`cross_collection_schema.sql` is an additive migration for researcher-reviewed links between edition-specific narration records. Apply it after the base schema has been initialized:

```bash
python -c "from cross_collection import apply_migration; apply_migration('hadith_records.db')"
```

It adds reviewed narration relationship groups, independent chain records and directional cross-references with relation types and review status. It **does not** merge narrations or chains, and it does not create factual links automatically. Populate only from curated, sourced research data. `cross_collection.py` exposes read helpers for related narrations and independent chains.

## Run tests

```bash
python -m unittest discover -s tests -v
```
