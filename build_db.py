import sqlite3
import json
import urllib.request
import codecs
import os
import sys
import re
import zlib

# Configure stdout to use utf-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "verbs.db"
KAIKKI_URL = "https://kaikki.org/dictionary/Italian/kaikki.org-dictionary-Italian.jsonl"

VOWELS_MAP = {
    'à': 'a', 'á': 'a', 'è': 'e', 'é': 'e', 'ì': 'i', 'í': 'i', 'ò': 'o', 'ó': 'o', 'ù': 'u', 'ú': 'u',
    'À': 'A', 'Á': 'A', 'È': 'E', 'É': 'E', 'Ì': 'I', 'Í': 'I', 'Ò': 'O', 'Ó': 'O', 'Ù': 'U', 'Ú': 'U'
}

# One-syllable words whose final accent is standard spelling (è vs e, dà vs da, dì vs di). Wiktionary also
# marks stress on other one-vowel words (fà, và, stò, fù), which Italian writes without an accent.
ACCENTED_MONOSYLLABLES = {"è", "dà", "dì", "sé", "né", "tè", "là", "lì", "sì"}

def _vowel_count(w: str) -> int:
    return sum(ch in "aeiouàáèéìíòóùú" for ch in w.lower())

def clean_accents(s: str) -> str:
    """Strip dictionary stress accents: internal ones, and final ones on monosyllables that take none (fà -> fa)."""
    if not s:
        return s
    def clean_single_word(w: str) -> str:
        chars = list(w)
        for i in range(len(chars) - 1):
            if chars[i] in VOWELS_MAP:
                chars[i] = VOWELS_MAP[chars[i]]
        word = "".join(chars)
        if word and word[-1] in VOWELS_MAP and _vowel_count(word) == 1 and word.lower() not in ACCENTED_MONOSYLLABLES:
            word = word[:-1] + VOWELS_MAP[word[-1]]
        return word
    return " ".join(clean_single_word(w) for w in s.split())

def clean_parentheses(s: str) -> str:
    """Remove parenthesized qualifiers (e.g. '(rare) arrabbiare' -> 'arrabbiare')."""
    if not s:
        return s
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

# Moods and tenses person mappings
PERSON_MAPPING = [
    ({"first-person", "singular"}, "io"),
    ({"second-person", "singular"}, "tu"),
    ({"third-person", "singular"}, "lui, lei, Lei, egli"),
    ({"first-person", "plural"}, "noi"),
    ({"second-person", "plural"}, "voi"),
    ({"third-person", "plural"}, "loro, Loro, essi")
]

# Tags Wiktionary puts on non-standard alternatives inside a conjugation table.
MARKED_TAGS = {"archaic", "obsolete", "literary", "poetic", "dialectal", "regional", "rare", "colloquial", "uncommon", "nonstandard", "Tuscany", "Southern-Italy", "Northern-Italy", "Rome", "Traditional", "proscribed"}

def standard_conjugation_forms(forms):
    """
    The forms of the entry's first conjugation table, standard forms before marked alternatives.

    Wiktionary pages often carry several it-conj tables one after the other: the standard one first,
    then tables of archaic, literary or regional forms (e.g. andare: vo, fare: fazzo, essere: so/ene),
    often without tags. Only the first table is the standard conjugation.
    """
    first_table = []
    tables = 0
    for f in forms:
        if f.get("source") != "conjugation":
            continue
        if "inflection-template" in f.get("tags", []):
            tables += 1
            if tables > 1:
                break
            continue
        first_table.append(f)
    # Stable sort: within a slot, an unmarked form comes before any marked alternative.
    return sorted(first_table, key=lambda f: bool(MARKED_TAGS & set(f.get("tags", []))))

def is_primary_entry(entry):
    """False when every sense only points to another word (alternative form, misspelling, inflection of)."""
    for sense in entry.get("senses", []):
        tags = set(sense.get("tags", []))
        if not ("alt_of" in sense or "form_of" in sense or tags & {"alt-of", "form-of", "misspelling"}):
            return True
    return False

# Sense tags of verbs that are not current standard Italian (gire "to go": archaic, dialectal, literary).
OLD_SENSE_TAGS = {"archaic", "obsolete", "literary", "poetic", "dialectal", "regional"}

def is_modern_entry(entry):
    """True when some sense is a current standard meaning, not an alternative form or an archaic/dialect use."""
    for sense in entry.get("senses", []):
        tags = set(sense.get("tags", []))
        if "alt_of" in sense or "form_of" in sense or tags & ({"alt-of", "form-of", "misspelling"} | OLD_SENSE_TAGS):
            continue
        return True
    return False

# Reverse lookup priorities (forms.priority): a form found in several verbs resolves to the lowest.
FORM_PRIORITY_STANDARD = 0  # a "form of" entry, or a standard-table form of a modern verb
FORM_PRIORITY_VARIANT = 1   # an alternative-table or marked form of a modern verb
FORM_PRIORITY_OLD = 2       # a form of an archaic, dialect or alternative-form verb
FORMS_UPSERT = ("INSERT INTO forms VALUES (?, ?, ?) "
                "ON CONFLICT(form, infinitive) DO UPDATE SET priority = MIN(priority, excluded.priority)")

def _set_principal(principal_forms, key, value):
    if principal_forms.get(key, "—") == "—":
        principal_forms[key] = value

def extract_conjugations_and_metadata(entry):
    """
    Extracts the auxiliary, model, principal forms, and simple conjugation table from a verb entry.
    """
    forms = entry.get("forms", [])
    word = clean_parentheses(clean_accents(entry.get("word", "")))
    
    # Find auxiliary
    auxiliary = "avere"
    for f in forms:
        if "auxiliary" in f.get("tags", []):
            auxiliary = clean_parentheses(clean_accents(f.get("form", "avere")))
            break
            
    # Determine model from head template if possible
    model = word
    if "head_templates" in entry:
        for ht in entry["head_templates"]:
            if ht.get("name") == "it-verb":
                break
                
    principal_forms = {
        "infinito": word,
        "gerundio": "—",
        "participio passato": "—",
        "participio presente": "—"
    }
    
    # Initialize basic conjugation structure
    conjugations = {
        "indicativo": {
            "presente": {},
            "imperfetto": {},
            "passato remoto": {},
            "futuro semplice": {}
        },
        "congiuntivo": {
            "presente": {},
            "imperfetto": {}
        },
        "condizionale": {
            "presente": {}
        },
        "imperativo": {
            "presente": {}
        }
    }
    
    has_conjugations = False
    
    # Parse each form of the standard conjugation table (first form per slot wins)
    for f in standard_conjugation_forms(forms):
        tags = set(f.get("tags", []))
        form_val = clean_accents(f.get("form", ""))
        if not form_val:
            continue
            
        # Principal forms
        if "gerund" in tags:
            _set_principal(principal_forms, "gerundio", form_val)
        elif "participle" in tags and "past" in tags:
            _set_principal(principal_forms, "participio passato", form_val)
        elif "participle" in tags and "present" in tags:
            _set_principal(principal_forms, "participio presente", form_val)
            
        # Indicativo Presente
        if "indicative" in tags and "present" in tags:
            for tag_set, person in PERSON_MAPPING:
                if tag_set.issubset(tags):
                    conjugations["indicativo"]["presente"].setdefault(person, form_val)
                    has_conjugations = True
                    
        # Indicativo Imperfetto
        elif "indicative" in tags and "imperfect" in tags:
            for tag_set, person in PERSON_MAPPING:
                if tag_set.issubset(tags):
                    conjugations["indicativo"]["imperfetto"].setdefault(person, form_val)
                    has_conjugations = True
                    
        # Indicativo Passato Remoto
        elif "indicative" in tags and "historic" in tags and "past" in tags:
            for tag_set, person in PERSON_MAPPING:
                if tag_set.issubset(tags):
                    conjugations["indicativo"]["passato remoto"].setdefault(person, form_val)
                    has_conjugations = True
                    
        # Indicativo Futuro Semplice
        elif "indicative" in tags and "future" in tags:
            for tag_set, person in PERSON_MAPPING:
                if tag_set.issubset(tags):
                    conjugations["indicativo"]["futuro semplice"].setdefault(person, form_val)
                    has_conjugations = True
                    
        # Congiuntivo Presente
        elif "subjunctive" in tags and "present" in tags:
            for tag_set, person in PERSON_MAPPING:
                if tag_set.issubset(tags):
                    conjugations["congiuntivo"]["presente"].setdefault(person, form_val)
                    has_conjugations = True
                    
        # Congiuntivo Imperfetto
        elif "subjunctive" in tags and "imperfect" in tags:
            for tag_set, person in PERSON_MAPPING:
                if tag_set.issubset(tags):
                    conjugations["congiuntivo"]["imperfetto"].setdefault(person, form_val)
                    has_conjugations = True
                    
        # Condizionale Presente
        elif "conditional" in tags and "present" in tags or ("conditional" in tags and not any(t in tags for t in ["past", "perfect"])):
            for tag_set, person in PERSON_MAPPING:
                if tag_set.issubset(tags):
                    conjugations["condizionale"]["presente"].setdefault(person, form_val)
                    has_conjugations = True
                    
        # Imperativo Presente
        elif "imperative" in tags and "present" in tags or ("imperative" in tags and "negative" not in tags):
            # Lei/Loro forms are third-person (second-person-semantically). "formal" alone also tags the
            # traditional-stress variant of a tu form (valùta next to vàluta), which is not a Lei form.
            is_formal = "third-person" in tags or "second-person-semantically" in tags
            
            # Map second person singular
            if "singular" in tags:
                if "second-person" in tags and not is_formal:
                    conjugations["imperativo"]["presente"].setdefault("(tu)", form_val)
                    has_conjugations = True
                elif is_formal or "third-person" in tags:
                    conjugations["imperativo"]["presente"].setdefault("(Lei)", form_val)
                    has_conjugations = True
            elif "plural" in tags:
                if "first-person" in tags:
                    conjugations["imperativo"]["presente"].setdefault("(noi)", form_val)
                    has_conjugations = True
                elif "second-person" in tags:
                    conjugations["imperativo"]["presente"].setdefault("(voi)", form_val)
                    has_conjugations = True
                elif is_formal or "third-person" in tags:
                    conjugations["imperativo"]["presente"].setdefault("(Loro)", form_val)
                    has_conjugations = True
                    
    return auxiliary, model, principal_forms, conjugations, has_conjugations

def build_database(source_file=None):
    """Build verbs.db from the kaikki.org dump: streamed from KAIKKI_URL, or read from `source_file`."""
    # Remove existing DB if any to start fresh
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create tables (storing JSON as compressed BLOBs)
    cursor.execute("""
    CREATE TABLE verbs (
        infinitive TEXT PRIMARY KEY,
        conjugation_json BLOB,
        auxiliary TEXT,
        model TEXT,
        principal_forms_json BLOB
    )
    """)
    
    cursor.execute("""
    CREATE TABLE forms (
        form TEXT,
        infinitive TEXT,
        priority INTEGER,  -- reverse lookup prefers 0 (see FORM_PRIORITY_* below)
        PRIMARY KEY (form, infinitive)
    )
    """)
    
    cursor.execute("CREATE INDEX idx_forms_form ON forms(form)")
    cursor.execute("CREATE INDEX idx_forms_infinitive ON forms(infinitive)")
    conn.commit()
    
    print("Database tables and indexes created successfully.")
    
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(KAIKKI_URL, headers=headers)
    
    print(f"Reading Wiktionary data from {source_file or KAIKKI_URL}...")
    
    verbs_to_insert = []
    stored_rank = {}  # infinitive -> rank of its stored entry (see is_primary_entry)
    forms_to_insert = {}  # (form, infinitive) -> best priority

    def add_form(form, infinitive, priority):
        key = (form, infinitive)
        if priority < forms_to_insert.get(key, priority + 1):
            forms_to_insert[key] = priority
    
    line_count = 0
    verb_count = 0
    form_ref_count = 0
    
    try:
        with (open(source_file, encoding="utf-8") if source_file else urllib.request.urlopen(req)) as response:
            reader = response if source_file else codecs.getreader("utf-8")(response)
            
            for line in reader:
                line_count += 1
                if line_count % 50000 == 0:
                    print(f"Processed {line_count} lines. Saved {verb_count} verbs...")
                    
                try:
                    entry = json.loads(line)
                    if entry.get("pos") != "verb":
                        continue
                        
                    word = clean_parentheses(clean_accents(entry.get("word", "")))
                    if not word:
                        continue
                        
                    # Extract conjugations first
                    auxiliary, model, principal_forms, conjugations, has_conjugations = extract_conjugations_and_metadata(entry)
                    
                    # Check if it's a form-of entry
                    is_form_of = False
                    form_of_verbs = []
                    
                    senses = entry.get("senses", [])
                    for sense in senses:
                        if "form_of" in sense:
                            is_form_of = True
                            for fo in sense["form_of"]:
                                fword = clean_parentheses(clean_accents(fo.get("word")))
                                if fword:
                                    form_of_verbs.append(fword)
                                    
                    if "form_of" in entry:
                        is_form_of = True
                        for fo in entry["form_of"]:
                            fword = clean_parentheses(clean_accents(fo.get("word")))
                            if fword:
                                form_of_verbs.append(fword)
                                
                    if is_form_of and not has_conjugations:
                        for fv in form_of_verbs:
                            add_form(word, fv, FORM_PRIORITY_STANDARD)
                            form_ref_count += 1
                        continue
                        
                    # Store verb as a main verb entry (compress JSONs with zlib). Homonyms come as separate
                    # entries with the same infinitive (partire "to leave", then partire "to divide"; notare
                    # "alternative form of nuotare", then notare "to notice"). The first entry wins unless a
                    # later one ranks higher: a table beats none, a real meaning beats an alternative form.
                    rank = (has_conjugations, has_conjugations and is_primary_entry(entry))
                    if has_conjugations or "head_templates" in entry:
                        if word not in stored_rank or rank > stored_rank[word]:
                            stored_rank[word] = rank
                            comp_conj = zlib.compress(json.dumps(conjugations, ensure_ascii=False).encode('utf-8'))
                            comp_pf = zlib.compress(json.dumps(principal_forms, ensure_ascii=False).encode('utf-8'))
                            verbs_to_insert.append((
                                word,
                                sqlite3.Binary(comp_conj),
                                auxiliary,
                                model,
                                sqlite3.Binary(comp_pf)
                            ))
                            verb_count += 1
                        
                        # Reverse lookup keeps every entry's forms, homonyms and alternative tables included,
                        # ranked so that "vado" finds andare before the archaic gire.
                        modern = is_modern_entry(entry)
                        standard = {id(f) for f in standard_conjugation_forms(entry.get("forms", []))
                                    if not MARKED_TAGS & set(f.get("tags", []))}
                        add_form(word, word, FORM_PRIORITY_STANDARD if modern else FORM_PRIORITY_OLD)
                        for fv in form_of_verbs:
                            add_form(word, fv, FORM_PRIORITY_STANDARD)
                        
                        for f in entry.get("forms", []):
                            if f.get("source") == "conjugation":
                                fval = clean_accents(f.get("form"))
                                if fval:
                                    priority = (FORM_PRIORITY_OLD if not modern else
                                                FORM_PRIORITY_STANDARD if id(f) in standard else FORM_PRIORITY_VARIANT)
                                    add_form(fval, word, priority)
                                    parts = fval.split()
                                    if len(parts) > 1:
                                        add_form(parts[-1], word, priority)
                                        
                    # Write in batches of 1000
                    if len(verbs_to_insert) >= 1000:
                        cursor.executemany(
                            "INSERT OR REPLACE INTO verbs VALUES (?, ?, ?, ?, ?)",
                            verbs_to_insert
                        )
                        verbs_to_insert.clear()
                        
                        cursor.executemany(FORMS_UPSERT, [(f, i, p) for (f, i), p in forms_to_insert.items()])
                        forms_to_insert.clear()
                        conn.commit()
                        
                except Exception as e:
                    pass
                    
    except Exception as e:
        print("Error during streaming:", e)
        conn.close()
        sys.exit(1)
        
    # Flush remaining batch
    if verbs_to_insert:
        cursor.executemany(
            "INSERT OR REPLACE INTO verbs VALUES (?, ?, ?, ?, ?)",
            verbs_to_insert
        )
    if forms_to_insert:
        cursor.executemany(FORMS_UPSERT, [(f, i, p) for (f, i), p in forms_to_insert.items()])
        
    conn.commit()
    # Compact the file: batched inserts leave free pages, and the DB must stay under GitHub's 100 MB limit.
    conn.execute("VACUUM")
    conn.close()
    
    print("Database build completed successfully!")
    print(f"Total lines processed: {line_count}")
    print(f"Total main verbs loaded: {verb_count}")
    print(f"Total reverse lookup forms loaded: {form_ref_count}")

if __name__ == "__main__":
    # Optional argument: a downloaded kaikki.org-dictionary-Italian.jsonl, instead of streaming it.
    build_database(sys.argv[1] if len(sys.argv) > 1 else None)
