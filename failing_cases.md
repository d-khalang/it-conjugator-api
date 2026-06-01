# Failing Cases & Improvements Checklist

This document tracks local testing failures, explains why they occurred, and outlines plans to address them.

---

## 1. Case: Spelling Typo
### Command
```cmd
python main.py "mi arrabbiavvo"
```
### Result
```
[ERROR] Verb 'mi arrabbiavvo' not found in offline database
```
### Analysis
* **Why it failed**: The input word `"arrabbiavvo"` has a spelling typo (two `v`s instead of one: `"arrabbiavo"`). Because the offline database is compiled from clean dictionary words and exact conjugations, it has no record of the misspelled word.
* **Impact**: Downstream clients (e.g., Telegram bot users typing spelling errors) will get a "not found" error.
* **Proposed Solution**: 
  * Add a fuzzy search fallback or Damerau-Levenshtein distance matching in `db_core.py` when an exact match is not found.
  * If the closest database form is within a small edit distance (e.g., 1 or 2 characters), the API could either:
    1. Auto-resolve to the closest word and return it with a warning note (e.g., `"note": "Showing results for 'mi arrabbiavo'"`).
    2. Return a list of suggested verbs (e.g., `"Did you mean: arrabbiare?"`).

---

## 2. Case: Windows Command Prompt Mistake
### Command
```cmd
"mi arrabbio"
```
### Result
```
'"mi arrabbio"' is not recognized as an internal or external command,
operable program or batch file.
```
### Analysis
* **Why it failed**: This is a command-line environment syntax mistake. The query `"mi arrabbio"` was entered directly into the terminal prompt without prefixing it with the Python execution script command `python main.py`.
* **Impact**: No impact on the application or API. This is purely a client-side interaction error.
* **Proposed Solution**: None required for the API/DB. Ensure the documentation clear-cut examples of CLI queries.

---

## 3. Case: Unquoted Multi-Word CLI Query
### Command
```cmd
python main.py mi arrabbio
```
### Result
```
[ERROR] Verb 'mi' not found in offline database
```
### Analysis
* **Why it failed**: The command line interpreter splits arguments on spaces. As a result:
  * `sys.argv[1]` = `"mi"`
  * `sys.argv[2]` = `"arrabbio"`
  
  The current CLI parser in `main.py` only reads `sys.argv[1]`, causing it to query `"mi"` (which is a reflexive clitic pronoun, not a verb in our verbs dictionary).
* **Impact**: Friction during local testing if the user forgets to wrap pronominal or conjugated multi-word inputs in double quotes.
* **Proposed Solution**: 
  * Update `main.py` to join all command-line arguments:
    ```python
    verb = " ".join(sys.argv[1:]).strip()
    ```
    This allows running `python main.py mi arrabbio` without any quotes.

---

## Action Plan

- [x] **Fix CLI Argument Parsing**: Modify `main.py` to support unquoted multi-word arguments.
- [x] **Clean Input Quotes**: Ensure the database query strips optional surrounding quotes (`"` or `'`) that might be accidentally passed down from command lines or query strings.
- [x] **Explore Fuzzy Matching Fallback**: Implement a lightweight edit-distance check on `forms` and `verbs` tables for spelling auto-correction.
