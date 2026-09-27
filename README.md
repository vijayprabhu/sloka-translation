# sloka-translation

Python tools for transliterating Vedic Sanskrit slokas into Tamil script, with phonetic marks that preserve correct pronunciation.

## Goals

Tamil script has one letter for each consonant family. For example, `க` covers ka / kha / ga / gha. Sanskrit keeps these four sounds apart. So Tamil editions of Vedic texts have to add extra markings, or the reader cannot tell which sound is meant. This repo covers both directions of that problem:

1. **Simplify existing Tamil sloka PDFs.** Many Tamil editions write a Latin hint in parentheses after each ambiguous letter, e.g. `க(ga)` or `த்(d)`. The tools here pull those hints out and classify each one by traditional Śikṣā phonetics. They then replace each hint with a compact superscript digit:
   - **2**: aspirated, unvoiced (kha, cha, ṭha, tha, pha)
   - **3**: unaspirated (ka, ga, ta, da, ...)
   - **4**: aspirated, voiced (gha, jha, ḍha, dha, bha)

   The result is a new PDF with the same layout, fonts, colors and Vedic accent marks as the original. Only the hints change: each one becomes a small digit placed next to the Tamil letter it marks.

2. **Convert accented Devanagari Sanskrit into Tamil.** Given Vedic Sanskrit in Devanagari (inline text, `.txt`, or `.pdf`), it produces Tamil script with:
   - the same 2/3/4 superscript-digit convention,
   - the Vedic stress accents (anudātta, svarita, double svarita) carried over,
   - correct anusvāra assimilation and visarga sandhi as used in recitation,
   - a PDF styled like the "Veda Study SSB" house layout (corner logos, page header, page-numbered footer).

## Setup

Requires Python 3 on macOS. PDF rendering uses the system fonts *Tamil MN* and *Geneva*.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dependencies: `pymupdf`, `aksharamukha`, `fonttools`.

## Usage

All outputs are written to `output/`, which is created automatically. Every script accepts `-o <filename>` to choose a different output filename (it still goes in `output/`).

### 1. Extract transliteration hints from a Tamil PDF

```
python src/extract_transliterations.py docs/GanapathiAthirvase.pdf
```

Writes every Latin `(term)` found in the PDF to `output/GanapathiAthirvase_terms.txt`.

### 2. Classify each hint as 2 / 3 / 4

```
python src/classify_transliterations.py docs/GanapathiAthirvase.pdf
```

Prints a `term<TAB>number` table and writes it to `output/GanapathiAthirvase_mapping.txt`.

Add `--replace` to also write a plain-text version with each `(term)` replaced by its number (`output/GanapathiAthirvase_replaced.txt`):

```
python src/classify_transliterations.py docs/GanapathiAthirvase.pdf --replace
```

### 3. Generate a replaced PDF that keeps the original layout

```
python src/generate_replaced_pdf.py docs/GanapathiAthirvase.pdf
```

Writes `output/GanapathiAthirvase_replaced.pdf`. It looks the same as the source, but each `(term)` has been replaced by its superscript digit and the rest of the line closed up to fill the gap.

### 4. Convert Devanagari Sanskrit to Tamil

Inline text:

```
python src/sanskrit_to_tamil.py 'भ॒द्रं᳚ कर्णे᳚भिः॑ शृ॒णुयाम॑ देवाः᳚'
```

From a file (`.pdf` or `.txt`), with a custom page-header title:

```
python src/sanskrit_to_tamil.py -f path/to/input.pdf --title "நாராயண ஸூக்தம்"
```

Writes `output/<input name>_tamil.txt` and `.pdf`, or `output/sanskrit_to_tamil_output.{txt,pdf}` for inline text.

Options:
- `--title "<text>"`: header text shown on every page of the styled PDF.
- `--plain-pdf`: produce a plain, text-only PDF without the Veda Study SSB styling.
- `--validate`: a diagnostic check that needs no input. It converts `docs/NarayanaSuktam_Sanskrit.pdf` and compares the result with `docs/NarayanaSuktam.pdf`, then prints a similarity score and sample mismatches. It is not a pass/fail test.

The input must already carry its accent marks. The script re-encodes whatever accents are present; it does not infer missing ones.

## Repository layout

| Path | Contents |
|---|---|
| `src/extract_transliterations.py` | Finds Latin/IAST `(term)` hints in a PDF; shared output-path helper |
| `src/classify_transliterations.py` | Maps each term to 2/3/4 by aspiration and voicing; optional text replacement |
| `src/generate_replaced_pdf.py` | Rebuilds the PDF page by page with the terms swapped for digits |
| `src/sanskrit_to_tamil.py` | Devanagari → Tamil conversion with accents, sandhi rules and styled PDF output |
| `docs/` | Sample source PDFs (Tamil with transliteration hints, plus a Sanskrit/Tamil Nārāyaṇa Sūktam pair) |
| `assets/` | Generated on first use: the corner logo and a `TamilMN.ttf` pulled out of the macOS font collection |
| `output/` | Generated files (not source) |

## Known limitations

- **macOS only for now.** PDF rendering loads Apple system fonts by path. To run on another OS, change `FALLBACK_FONT_PATH` in `sanskrit_to_tamil.py` to an open-license font such as Noto Sans, and provide a Tamil font.
- Some source PDFs use fonts whose internal character mapping is wrong (e.g. `Sanskrit2003`). The page looks correct, but the text read from it contains wrong characters in places, and those errors pass through into the output.
- `NarayanaSuktam.pdf` marks ambiguous consonants with parenthetical hints such as `(dho)`, while this project uses superscript digits. `--validate` therefore reports about 81% similarity; almost all of the difference comes from that one convention mismatch.

See [CLAUDE.md](CLAUDE.md) for detailed implementation notes.
