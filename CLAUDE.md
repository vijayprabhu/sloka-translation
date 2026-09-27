# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Commands

Run the transliteration extractor against a PDF (writes `output/<pdf name>_terms.txt`):

```
python src/extract_transliterations.py docs/GanapathiAthirvase.pdf
```

Classify each transliteration term by Sanskrit consonant aspiration/voicing (prints a `term<TAB>number` table and writes `output/<pdf name>_mapping.txt`):

```
python src/classify_transliterations.py docs/GanapathiAthirvase.pdf
```

Also replace every `(term)` in the plain extracted text with its number, written to `output/<pdf name>_replaced.txt`:

```
python src/classify_transliterations.py docs/GanapathiAthirvase.pdf --replace
```

Generate a PDF that mirrors the source document's layout and colors, but with each `(term)` replaced in place by its number, sized to match the base Tamil character it annotates (writes `output/<pdf name>_replaced.pdf`):

```
python src/generate_replaced_pdf.py docs/GanapathiAthirvase.pdf
```

Convert accented Vedic Sanskrit (Devanagari) into Tamil script, using the same digit/accent notation reverse-engineered above (writes `output/<input name>_tamil.txt` and `.pdf`, or `output/sanskrit_to_tamil_output.{txt,pdf}` for inline text):

```
python src/sanskrit_to_tamil.py 'भ॒द्रं᳚ कर्णे᳚भिः॑ शृ॒णुयाम॑ देवाः᳚'
python src/sanskrit_to_tamil.py -f path/to/input.pdf --title "நாராயண ஸூக்தம்"   # or .txt
```

By default the PDF is styled to match the "Veda Study SSB" house layout (logo in both top corners, centered header title repeated per page, "Veda Study SSB <page>" footer) — pass `--title` to set the header text, or `--plain-pdf` for an unstyled, text-only PDF instead.

Check conversion accuracy against the one ground-truth pair available (diagnostic only, not a hard gate — prints a similarity score and a sample of mismatches):

```
python src/sanskrit_to_tamil.py --validate
```

All four scripts accept `-o <filename>` to override the output filename; the file always lands under `output/` (created automatically).

## Architecture

- `src/extract_transliterations.py` — reads a PDF (via PyMuPDF/`fitz`), finds every `(...)` group in the extracted text, and keeps only groups made entirely of Latin letters (including IAST-style accented/diacritic characters, e.g. `ā`, `ī`, `ū`, `ṭ`, `ḍ`, `ś`). Non-Latin parenthesized content (e.g. stray native-script characters in parens) is filtered out. Also defines `resolve_output_path()`, shared by all three scripts, which resolves a filename to `output/<filename>` and creates the `output/` folder if needed.
- `src/classify_transliterations.py` — builds on the extractor to map each unique term to 2, 3, or 4 based on Sanskrit Śikṣā varga classification (alpaprāṇa vs. mahaprāṇa, voiced vs. unvoiced): no `h` in the term → **3** (alpaprāṇa); has `h` and the base consonant is unvoiced (`k, c, ṭ, t, p`) → **2**; has `h` and the base consonant is voiced (`g, j, ḍ, d, b`) → **4**. With `--replace`, it also substitutes every `(term)` occurrence in the plain extracted text with its number. Exposes `classify_term()`, reused by the PDF generator.
- `src/generate_replaced_pdf.py` — produces a format-preserving replaced PDF. For each page it merges text spans per line (a `(term)` can split across spans when a diacritic letter like `ṭ`/`ḍ` falls back to a different font than its surrounding parentheses) and locates each mapped term's bounding box. Since a digit is much narrower than e.g. `(bha)`, the gap it would leave is closed up:
  - Each output page is composed from clipped slices of the unmodified source page via `show_pdf_page()` (text stays vector/selectable; fonts, Vedic accent marks, inline images come along untouched). Lines are grouped into visual rows (`get_text("dict")` can split one row into several "lines", e.g. around an inline image); rows without terms are copied as-is. In a row with terms, the source is cut at each `(term)`, the term itself is simply never copied, and every slice after it is drawn shifted left by the cumulative width saved. Text beyond the row's right edge (e.g. a corner logo) stays put.
  - Zero-advance accent marks (`_`, `~`, ...) placed right after a term draw their ink leftward, over the term's `)`; the strips above/below the term's own box are therefore copied too, shifted with the following text, so those marks end up under/over the digit rather than being lost.
  - The digit is drawn via `insert_text()`, sized to match the base Tamil character immediately preceding the term (not the small annotation font), at the original annotation's own (raised) baseline — so it reads as a superscript to the top-right of the base character.
- `src/sanskrit_to_tamil.py` — the reverse direction: Devanagari Sanskrit → Tamil. Input can be raw text, or a `.pdf`/`.txt` file (`-f`). Uses the `aksharamukha` library for the base Devanagari→Tamil conversion, which conveniently already marks ambiguous consonants with the same 2/3/4 superscript-digit convention derived above. Requires already-accented Devanagari input — it re-encodes whatever accents are present rather than inferring them.
  - Accent marks: standard Unicode Vedic stress marks (anudatta `॒` U+0952, svarita `॑` U+0951, double svarita `᳚` U+1CDA) are normalized to the custom combining codepoints the source PDF's font actually uses (U+0331, U+030D, U+030E) — "Veda Study SSB"-style source PDFs already use these custom codepoints directly, so that step is a no-op for them.
  - Those exact codepoints are also `aksharamukha`'s own internal escape targets for its Tamil output, so feeding them back in as input confuses its Devanagari parser (observed corrupting a consonant's varga-position digit, e.g. `भु` came out as `பு³` instead of the correct `பு⁴`). Fix: the text is split on the 5 known accent characters first, each mark-free segment is transliterated independently, and the marks are spliced back in unchanged between segments — `aksharamukha` never sees them mixed into Devanagari input.
    - That per-segment isolation has its own side effect: it can sever an anusvara from the very consonant it should assimilate to, whenever an accent mark falls between them (common in real texts, e.g. `सं॒कर` splits into `सं` / `कर`) — aksharamukha never sees the following consonant and falls back to the generic anusvara `ம்ʼ` instead of nasalizing (e.g. to `ங்`). Fix: each segment is transliterated together with one character of lookahead borrowed from the next non-empty segment, then that lookahead character's own (separately computed) rendering is stripped off the end of the result — whatever remains is the segment's own output, now with cross-boundary assimilation intact. Falls back to transliterating the segment alone if the lookahead's rendering isn't found as a clean suffix (e.g. it forms a ligature whose shape isn't just its own rendering appended).
  - Visarga (`ः`) sandhi: `aksharamukha` leaves visarga as a plain `꞉` in every context (confirmed: no assimilation happens on its own). Two traditional Vedic-recitation realizations are rewritten on the raw Devanagari text before transliteration (`apply_visarga_rules()`), so aksharamukha's own correct consonant/vowel handling does the rest: visarga before `श/ष/स` assimilates fully to that sibilant, doubling it (`रामः शेते` → `रामश् शेते` → `ராமஶ் ஶேதே`); visarga before a vowel-initial word echoes the vowel on the immediately preceding syllable through a `ह` (`देवाः अपि` → `देवाहा अपि` → `தேவாஹா அபி`; bare/inherent "a" → plain `ह`). A gap of whitespace and/or accent marks between the visarga and its trigger is tolerated, for the same reason accent marks commonly split anusvara from its context above.
  - PDF output: PyMuPDF/MuPDF's own text insertion draws glyphs one at a time with no font-fallback or diacritic-stacking — no single font (Tamil MN, a general-coverage fallback, etc.) contains every codepoint this script emits. Fix: `_draw_body()` (shared by `render_pdf()`/`render_pdf_styled()`) does its own layout — for each character it picks whichever of two `fitz.Font`s actually has the glyph (`TamilMN.ttf` for ordinary Tamil, a fallback font for combining accent marks/superscript digits/visarga colon), word-wraps using real per-glyph advance widths (`Font.glyph_advance()`), and manually stacks combining marks above/below the preceding base glyph (centered over its advance, offset by the mark's Unicode combining class, drawn smaller than body text). Pure PyMuPDF + `fontTools`, no new dependency, no shell-out, no OS-specific renderer — the previous approach shelled out to macOS's `cupsfilter` (CoreText's `cgtexttopdf` filter), whose fixed-pitch (typewriter-grid) layout model was confirmed by direct repro to catastrophically over-wrap real body text into near one-glyph-per-line garbage, since Tamil's variable glyph widths don't fit a fixed-column assumption at all — not a tunable-parameter problem, the renderer itself was wrong for this content.
    - The fallback font is `/System/Library/Fonts/Geneva.ttf`, confirmed (by checking each actually-used codepoint's cmap, not just eyeballing) to cover every non-Tamil codepoint this script emits. `Arial Unicode.ttf` looked complete by eye but is actually missing the visarga colon (U+A789) and double-kampa (U+034C) — checking `Font.has_glyph()` alone didn't catch this, since macOS's `LastResort.otf` "unknown glyph" placeholder font *also* reports having every codepoint (it draws a box, never a real glyph) and was accidentally treated as evidence of coverage during testing. Both fallback fonts are Apple-licensed, so they're referenced by system path rather than bundled into the repo; the renderer itself is otherwise platform-agnostic — swap `FALLBACK_FONT_PATH` for an open-license font (e.g. Noto Sans) to run elsewhere.
    - Tamil script itself needs no complex-script reordering/shaping here: unlike Devanagari's pre-base vowel signs, the Tamil vowel signs this script's output uses render in plain left-to-right codepoint order (confirmed against `docs/NarayanaSuktam.pdf`'s own rendering) — simple per-character drawing at computed positions is sufficient, no HarfBuzz/shaping-engine dependency needed.
  - `render_pdf_styled()` (the default) replicates the "Veda Study SSB" house style reverse-engineered from `docs/NarayanaSuktam.pdf`: page size/margins, the logo image in both top corners (extracted once to `assets/veda_study_logo.jpg`), a centered header title repeated per page, and a "Veda Study SSB \<page\>" footer — all drawn directly with PyMuPDF, with `_draw_body()` starting a new templated page whenever body text would overflow the current one.
  - `strip_repeated_boilerplate()` removes a source PDF's own running title/footer noise (which would otherwise sit duplicated inside the body flow once our own header/footer template is layered on) by dropping blank lines, any line containing "Veda Study SSB", and any line that's an exact repeat of one already seen (the title repeats verbatim on every page) — only applied when reading from a file (`-f`), not for a short inline mantra.
  - `--validate` (no input needed) runs `docs/NarayanaSuktam_Sanskrit.pdf` through the full pipeline and diffs the result against `docs/NarayanaSuktam.pdf`'s own text character-by-character (`difflib.SequenceMatcher`, not line-by-line — line breaks don't land in the same places in both, which makes line-level comparison nearly useless), reporting an overall similarity score and a sample of non-artifact mismatches (mismatches touching a known shared cmap-artifact token, see below, are bucketed out separately). Diagnostic only, not a pass/fail gate. Currently ~81% character-level similarity; nearly all of the remaining "real" mismatches turn out to be one single systematic difference, not scattered phonetic errors: `docs/NarayanaSuktam.pdf`'s own house style spells out ambiguous consonants with literal parenthetical Latin hints (`(dho)`, `(bhi)`, `(kha)`, ...) rather than this script's superscript-digit convention (`⁴`, `²`, ...) — the digit convention is this project's own shorthand (originally derived from `classify_transliterations.py` replacing GanapathiAthirvase's own parenthetical hints with digits), not something `NarayanaSuktam.pdf` itself uses. Not fixed here — reconciling the two conventions would mean teaching this script to also emit parenthetical hints, a separate feature.
  - Known gap vs. the source PDF's full phonetic notation (not modeled): no anusvara-to-nasal assimilation before semivowels/sibilants/h/vowels (linguistically correct to leave as generic anusvara there — assimilation only applies before the 5 stop-consonant classes, which `aksharamukha` already handles, see above). The `kampa` wobble marks (`͂`/`͌`) pass through correctly since they're literal codepoints in the input. Line-wrap positions won't exactly match the source (different input text, different length, and now genuinely re-flowed rather than shelled out) — only the overall margins/scale/branding do.
  - Caveat: some source PDFs use fonts with non-standard Unicode cmaps (e.g. `Sanskrit2003`, seen in `NarayanaSuktam_Sanskrit.pdf`), where `get_text()` returns incorrect codepoints for some glyphs despite correct visual rendering — a text-layer fidelity issue in the source file, not in this script's conversion logic. Confirmed the *same* family of stray tokens (`n`, `u`, `f`, `s`, `ñ`, `gṁ`, ...) shows up at matching positions in both `NarayanaSuktam_Sanskrit.pdf`'s and `NarayanaSuktam.pdf`'s own extracted text, meaning `NarayanaSuktam.pdf` inherits the same defect rather than being a clean gold text for those specific tokens (hence `--validate` buckets them out rather than reporting them as conversion errors).
- `docs/` — source PDFs to process. These are native-script documents (e.g. Tamil) with inline Latin transliteration hints in parentheses next to each character, such as `க(ga)` or `த்(d)`.
- `assets/` — extracted at runtime by `sanskrit_to_tamil.py` on first use: `veda_study_logo.jpg` (the corner logo, pulled from `docs/NarayanaSuktam.pdf`) and `TamilMN.ttf` (a standalone face extracted from the macOS system font collection `/System/Library/Fonts/Supplemental/Tamil MN.ttc`, since PyMuPDF can't load `.ttc` directly).
- `output/` — generated files from the scripts above (git-ignorable; not committed source).
