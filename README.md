# it-conjugator-api

A lightweight, high-performance, 100% offline API and SQLite database service for Italian verb conjugations.

This project replaces live web scrapers (which are susceptible to Cloudflare/WAF IP blocks on VPS environments) and offline machine-learning packages (which often fail to conjugate reflexive and pronominal verbs accurately).

## Features

- **100% Offline**: Serves conjugations directly from a local, pre-compiled SQLite database (`verbs.db`).
- **Complete Verb Coverage**: Contains **48,641 main verbs** and **748,513 reverse lookup forms**.
- **Reverse Lookup Support**: Automatically resolves inflected/conjugated forms (e.g. `dico`) back to their root infinitives (`dire`).
- **Pronominal & Reflexive Verbs**: Accurately handles reflexive verbs (e.g. `arrabbiarsi`), double clitics (e.g. `tirarsela`), and compound pronominal verbs (e.g. `mettercela`) with proper clitic contraction (e.g. *ce l'ho messa*) and past participle agreement.
- **Accent Cleaning**: Helper accents used for pronunciation guides in dictionaries are automatically stripped for clean standard output.
- **Embedded Database**: The SQLite file is compressed with `zlib` columns, bringing it down to a compact ~92 MB file which is safely under GitHub's 100 MB limit.

## API Setup

### Requirements
- Python 3.10+
- FastAPI
- Uvicorn

Install dependencies:
```bash
pip install -r requirements.txt
```

Set the required API key environment variable:
* **Windows (PowerShell)**:
  ```powershell
  $env:SCRAPER_API_KEY="secret_auth"
  ```
* **Windows (CMD)**:
  ```cmd
  set SCRAPER_API_KEY=secret_auth
  ```
* **Linux / macOS**:
  ```bash
  export SCRAPER_API_KEY="secret_auth"
  ```

Run the service:
```bash
python -m uvicorn app.api:app --host 0.0.0.0 --port 8000
```

Once running, query the API using standard HTTP tools (such as curl):
```bash
curl -H "X-API-Key: secret_auth" "http://localhost:8000/conjugate?v=mi+arrabbio"
```

### API v2

Service-to-service API for the Kartino Verbs page (same `X-API-Key` header). The shared contract lives in the app
repo (`docs/verbs/contract.md`); `tests/fixtures/conjugator/` holds its fixtures, which the tests reproduce.
v1 `/conjugate` is unchanged.

| Route | Answer |
|-------|--------|
| `GET /v2/conjugate?q=` | `{"match", "verb"}`; 404 `{"error": {"code": "verb_not_found", ...}, "suggestions"}`; 400 `invalid_query` |
| `GET /v2/suggest?q=&limit=8` | `{"items": [infinitive]}`, prefix match; `q` shorter than 2 → `[]` |
| `POST /v2/infinitives` `{"words": [...]}` (≤ 500) | `{"infinitives": {word: infinitive or null}}`: infinitives only |

- **Verb object**: canonical ids (`indicativo-presente`, persons `1s`…`3p`, imperativo `2s`…`3p`), compound indicative
  tenses under `indicativo` with `compound: true`, every slot a list of forms (one `primary`). Essere compounds add a
  feminine variant. Defective slots are `[]`; a tense with no forms is left out.
- **Stem/ending** (`app/v2/grammar.py`, pure): the regular form comes from the verb class (-are, -ere, -ire, -ire with
  -isc-, -rre) with the spelling rules (-care/-gare, -ciare/-giare/-sciare, -iare). The longest fitting candidate ending
  (the slot's regular ending, or a core ending of the tense and person across classes) splits the form; flags compare
  with the regular stem and ending. -ere passato remoto -etti/-ette/-ettero count as regular.
  Clitics before the verb go in `parts.clitic` (`mi`, `me ne`, `ce l'`); pronouns attached after it go in
  `parts.enclitic`, split on the base form: `svegli|a|ti`, `v|a|ttene`, `and|iamo|cene`.
- **Match**: `infinitive` (the query is one), `form` (every slot holding it; works with spaces: `sono andato`,
  `mi alzo`, `me ne vado`, `ce l'ho fatta`), `fuzzy` (closest infinitives by edit distance). Queries: letters,
  spaces and apostrophes, at most 60 chars and 4 words.
- **Infinitives**: the ~13k entries of `verbs.db` with a conjugation table (loaded once into memory, ~1 s).
  A pronominal verb without its own table (`parlarne`, `lavarsela`) is not an infinitive for v2: v1's dynamic
  builder gets its forms wrong, so v2 answers null / not found. The other ~35k rows (`andandoci`, idioms) are not
  served by v2.
- **Suggest order**: `verbs.db` has no word frequencies, so the order is a stand-in: shorter base verb first, the base
  before its pronominal forms (`andare, andarne, andarsene, andicappare`). A real "most common first" needs a
  frequency list of Italian lemmas (e.g. a corpus count) stored as a rank per infinitive.
- **Variants**: the data has one form per slot; `app/v2/verb.py` adds the standard truncated tu-imperatives
  (`va'`, `da'`, `fa'`, `sta'`; the data already has `di'`). `DATA_VERSION` there is the build date of `verbs.db`: bump it on every rebuild.

### Tests
```bash
pip install pytest httpx
pytest
```

### Rebuilding `verbs.db`
```bash
python build_db.py                               # streams the kaikki.org Italian dump (~780 MB)
python build_db.py kaikki.org-dictionary-Italian.jsonl   # or reads a downloaded copy
```
How the build picks forms:
- **Standard table only**: a Wiktionary page often has several conjugation tables in a row (standard, then archaic or regional forms, often untagged). Only the first is used, and in each slot the first form wins, with archaic/literary/dialect-tagged forms last (*andare*: vado, not vò).
- **Homonyms**: the first entry with a table wins; a later one replaces it only if it has a table and the stored one is just an alternative form (*partire* "to leave", not "to divide"; *notare* "to notice", not "alternative form of nuotare").
- **Reverse lookup** prefers standard forms of current verbs (`forms.priority`): *vado* finds *andare*, not the archaic *gire*.
- **Accents**: dictionary stress marks are removed, including on one-vowel words (fà → fa, stò → sto); standard accents stay (è, dà, può, andò).

Check the result with `pytest` and keep the file under 100 MB (the build ends with `VACUUM`).

### Docker
Alternatively, run with Docker:
```bash
docker build -t it-conjugator-api .
docker run -p 8000:8000 it-conjugator-api
```

---

## Data Attribution & Credits

The underlying conjugation tables, forms, and dictionary mappings in this service are parsed and built from the machine-readable Italian dictionary dumps provided by **[Kaikki.org](https://kaikki.org/)**, which are extracted from **Wiktionary** using the `wiktextract` tool.

### Academic Citation
If you use this dataset or API in academic research, please cite the creator of the extraction tool:

> Tatu Ylonen: *Wiktextract: Wiktionary as Machine-Readable Structured Data*, Proceedings of the 13th Conference on Language Resources and Evaluation (LREC), pp. 1317-1325, Marseille, 20-25 June 2022.
