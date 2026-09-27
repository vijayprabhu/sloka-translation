#!/usr/bin/env python3
"""Convert accented Vedic Sanskrit (Devanagari) into Tamil script with the same
phonetic/accent notation reverse-engineered from docs/GanapathiAthirvase.pdf:

  - Ambiguous consonants (each Tamil letter covers up to 4 Sanskrit sounds) are
    marked with a superscript digit, same convention as classify_transliterations.py:
    no digit = default (e.g. ka/ta/pa), 2 = unvoiced aspirate (kha), 3 = voiced
    unaspirate (ga), 4 = voiced aspirate (gha). aksharamukha's Devanagari->Tamil
    scheme already produces this convention natively.
  - Vedic pitch accents are marked with the same combining glyphs used in the
    source PDF's custom font (not the standard Unicode Vedic block): anudatta ->
    combining macron below (U+0331), svarita -> combining vertical line above
    (U+030D), dependent/double svarita -> combining vertical line double above
    (U+030E), kampa -> combining tilde (U+0342), double kampa (U+034C).

Input may already use either the standard Unicode Vedic stress marks (U+0952
anudatta, U+0951 svarita, U+1CDA double svarita) or the custom codepoints above
directly (as "Veda Study SSB"-style source PDFs do) -- both are normalized to
the custom codepoints before transliteration. This script does not infer
accents on its own; it re-encodes whatever accents are present in the input.

Writes both a .txt file (raw Unicode) and a .pdf. No single font available here
contains every codepoint used, so the PDF renderer draws each glyph against
whichever of two fonts (a Tamil font, a broad-coverage fallback font) actually
has it, doing its own line-wrapping and combining-mark stacking -- see
`_draw_body()`. The fallback font is currently referenced from a macOS system
path (see FALLBACK_FONT_PATH); swap it for an open-license font to run
elsewhere.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import fitz
from aksharamukha import transliterate as tr

from extract_transliterations import resolve_output_path

# Standard Unicode Vedic stress marks -> the custom combining codepoints this
# project's source PDFs actually use.
PRE_REMAP = {
    "॒": "̱",  # anudatta -> combining macron below
    "॑": "̍",  # svarita -> combining vertical line above
    "᳚": "̎",  # double svarita -> combining vertical line double above
}

# These exact codepoints are also aksharamukha's own internal escape targets for
# its Tamil output (it emits "\_"/"\'"'\"' for U+0331/U+030D/U+030E). Feeding them
# back in as *input* confuses its Devanagari parser -- observed corrupting the
# varga-position digit of the consonant immediately after the mark (e.g. भु came
# out as "பு³" instead of the correct "பு⁴"). So instead of passing them through,
# the text is split on these marks, each mark-free segment is transliterated on
# its own, and the marks are re-spliced back in unchanged between segments.
ACCENT_CHARS = "̱̍̎͂͌"
SPLIT_RE = re.compile(f"([{ACCENT_CHARS}])")

# Visarga (ः) is left as a plain "꞉" by aksharamukha in every context (no sandhi
# applied). Two traditional Vedic-recitation realizations are rewritten on the
# *Devanagari* side, before any transliteration, so aksharamukha's own (already
# correct) consonant/vowel handling does the rest:
#   - visarga before श/ष/स assimilates fully to that sibilant, doubling it:
#     "रामः शेते" -> "रामश् शेते" -> ராமஶ் ஶேதே
#   - visarga before a vowel-initial word echoes the vowel that was on the
#     immediately preceding syllable through a "ह": "देवाः अपि" -> "देवाहा अपि"
#     -> தேவாஹா அபி (bare/inherent "a" -> plain "ह", e.g. "रामः अपि" -> "रामह अपि")
# A gap of whitespace and/or accent marks (either representation -- standard
# Unicode or this project's custom codepoints) between the visarga and its
# trigger is tolerated, since accent marks commonly land right after a visarga
# in real texts, same as they do after anusvara (see convert() below).
_VISARGA_GAP = r"[\s॒॑᳚" + ACCENT_CHARS + r"]*"
_MATRA = "ा-ौ"
_VOWEL_START = "ऄ-औ"
_VISARGA_SIBILANT_RE = re.compile(r"ः(" + _VISARGA_GAP + r")([शषस])")
_VISARGA_VOWEL_RE = re.compile(r"([" + _MATRA + r"]?)ः(" + _VISARGA_GAP + r")(?=[" + _VOWEL_START + r"])")


def apply_visarga_rules(text: str) -> str:
    text = _VISARGA_SIBILANT_RE.sub(lambda m: m.group(2) + "्" + m.group(1) + m.group(2), text)
    text = _VISARGA_VOWEL_RE.sub(lambda m: m.group(1) + "ह" + m.group(1) + m.group(2), text)
    return text


def extract_devanagari_text(path: str) -> str:
    if path.lower().endswith(".pdf"):
        with fitz.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    with open(path, encoding="utf-8") as f:
        return f.read()


def strip_repeated_boilerplate(text: str) -> str:
    """Drop a source PDF's own running header/footer noise (repeated on every
    page, e.g. the title line and a "Veda Study SSB <n>" footer) before we lay
    the text out under our own header/footer/logo template -- otherwise the
    source's boilerplate ends up duplicated inside the body flow. Exact-duplicate
    lines (the title repeats verbatim every page) are dropped after their first
    occurrence; a real line-for-line refrain elsewhere in the text would also be
    dropped by this heuristic, which is an accepted tradeoff.
    """
    seen: set[str] = set()
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or "Veda Study SSB" in stripped:
            continue
        if stripped in seen:
            continue
        seen.add(stripped)
        kept.append(stripped)
    return "\n".join(kept)


def convert(devanagari_text: str) -> str:
    devanagari_text = apply_visarga_rules(devanagari_text)
    normalized = "".join(PRE_REMAP.get(ch, ch) for ch in devanagari_text)
    pieces = SPLIT_RE.split(normalized)

    # pieces alternates [text, mark, text, mark, ..., text] (SPLIT_RE captures the
    # single-char marks; a text segment between two adjacent marks can be empty).
    # Splitting in isolation avoids aksharamukha's escape-sequence corruption on
    # these codepoints (see ACCENT_CHARS comment above), but it can also sever an
    # anusvara from the consonant it should assimilate to when an accent mark
    # lands between them (e.g. "सं॒कर" splits "सं" away from "कर", so aksharamukha
    # never sees the "क" and can't nasalize -- confirmed to silently produce the
    # generic "ம்ʼ" anusvara instead of the correct "ங்"). Fix: transliterate each
    # text segment together with one character of lookahead from the next
    # non-empty segment, then strip that lookahead character's own (separately
    # computed) rendering off the end of the result -- whatever's left is the
    # segment's own output, now with correct cross-boundary assimilation. Falls
    # back to transliterating the segment alone if the lookahead character's
    # rendering isn't found as a clean suffix (e.g. it forms a ligature/conjunct
    # whose shape isn't just "its own rendering appended").
    def next_lookahead_char(start: int) -> str:
        for j in range(start, len(pieces), 2):
            if pieces[j]:
                return pieces[j][0]
        return ""

    out = []
    for i, piece in enumerate(pieces):
        if i % 2 == 1:
            out.append(piece)
            continue
        if not piece:
            continue
        lookahead = next_lookahead_char(i + 2)
        if lookahead:
            combined = tr.process("Devanagari", "Tamil", piece + lookahead)
            lookahead_alone = tr.process("Devanagari", "Tamil", lookahead)
            if lookahead_alone and combined.endswith(lookahead_alone):
                out.append(combined[: len(combined) - len(lookahead_alone)])
                continue
        out.append(tr.process("Devanagari", "Tamil", piece))
    return "".join(out)


# Layout constants reverse-engineered from docs/NarayanaSuktam.pdf (the
# "Veda Study SSB" house style): US Letter page, 72pt side margins, a small
# circular logo in each top corner, and a "Veda Study SSB <page>" footer.
PAGE_W, PAGE_H = 612, 792
MARGIN_L, MARGIN_R = 72, 72
BODY_RECT = fitz.Rect(MARGIN_L, 72, PAGE_W - MARGIN_R, PAGE_H - 72)
LOGO_LEFT_RECT = fitz.Rect(45.7, 16.65, 90.3, 60.5)
LOGO_RIGHT_RECT = fitz.Rect(518.85, 16.8, 563.45, 60.65)
FOOTER_Y = 737
BODY_FONT_SIZE = 11
MARK_FONT_SIZE = 7  # smaller than body text -- these are diacritics, not letters
LINE_HEIGHT = 14  # matches the source's body text scale
LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "veda_study_logo.jpg"
TAMIL_FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "TamilMN.ttf"
# TamilMN has no glyphs for the combining accent marks, superscript digits, or
# visarga colon this script emits (that's why CoreText/cupsfilter's automatic
# font-fallback was used previously). Confirmed present on macOS and confirmed
# (via each codepoint's cmap, not just visual inspection) to cover every
# non-Tamil codepoint this script uses -- Arial Unicode.ttf was tried first and
# looked complete by eye but turned out to be missing the visarga colon (U+A789)
# and double-kampa (U+034C), which silently fall back to nothing being missing
# only because LastResort.otf (macOS's "unknown glyph" placeholder font, never
# a real rendering choice) also reports having every codepoint. Bundled-font
# licensing means this stays a system path rather than a repo asset -- the
# renderer itself is otherwise platform-agnostic (no more shelling out to
# cupsfilter); swap this path for an open-license font to run elsewhere.
FALLBACK_FONT_PATH = "/System/Library/Fonts/Geneva.ttf"

_WORD_SPLIT_RE = re.compile(r"(\s+)")


def _ensure_tamil_font() -> Path:
    """Extract a standalone Tamil MN face from the macOS system font collection,
    for drawing ordinary Tamil letters -- confirmed to render correctly (no
    reordering/ligature issues observed for this script's output) without any
    shaping engine, unlike the accent marks/digits/visarga colon handled by the
    fallback font below."""
    if TAMIL_FONT_PATH.exists():
        return TAMIL_FONT_PATH
    from fontTools.ttLib import TTCollection

    TAMIL_FONT_PATH.parent.mkdir(parents=True, exist_ok=True)
    coll = TTCollection("/System/Library/Fonts/Supplemental/Tamil MN.ttc")
    coll.fonts[0].save(str(TAMIL_FONT_PATH))
    return TAMIL_FONT_PATH


def _ensure_fallback_font() -> str:
    path = Path(FALLBACK_FONT_PATH)
    if not path.exists():
        raise RuntimeError(
            f"Fallback font not found at {path} -- needed to draw the combining "
            "Vedic accent marks, superscript digits and visarga colon that "
            "TamilMN.ttf doesn't contain. macOS-only for now; see FALLBACK_FONT_PATH."
        )
    return str(path)


def _clusters(token: str) -> list[tuple[str, list[str]]]:
    """Split into (base_char, [floating_marks]) pairs -- a run of our 5 known
    Vedic accent marks (ACCENT_CHARS) attaches to the preceding base character.

    Deliberately checks membership in ACCENT_CHARS, not the generic Unicode
    combining-class test (`unicodedata.combining(ch) != 0`): Tamil's own
    virama/pulli (U+0BCD, the mark that turns "ஸர" into "ஸ்ர") also has a
    nonzero combining class, and a first version of this function using the
    generic test misclassified it as a floating accent mark -- drawing it
    tiny, offset above/below, and in the wrong (fallback) font instead of
    inline in the Tamil font, which is what actually produced the "garbled,
    unreadable" PDF output a user reported. Virama and every other Tamil vowel
    sign are ordinary base characters here, not accent marks.
    """
    clusters: list[tuple[str, list[str]]] = []
    for ch in token:
        if ch in ACCENT_CHARS and clusters:
            clusters[-1][1].append(ch)
        else:
            clusters.append((ch, []))
    return clusters


def _draw_body(
    doc: fitz.Document,
    text: str,
    *,
    styled: bool,
    title: str | None,
    tamil_font_path: str,
    fallback_font_path: str,
) -> None:
    """Lay out and draw `text` into `doc`, adding pages as needed.

    Does its own word-wrapping from real per-glyph advance widths (via
    `fitz.Font`, queried against whichever of the two fonts actually has each
    glyph), and manually stacks combining accent marks above/below the
    preceding base glyph (centered over its advance, offset by the mark's
    Unicode combining class) since PyMuPDF's own text insertion has no
    font-fallback or mark-positioning of its own. This replaces the previous
    cupsfilter-based renderer, whose fixed-pitch (typewriter-grid) layout
    assumption doesn't fit Tamil's variable glyph widths at all -- confirmed by
    direct repro to catastrophically over-wrap real body text into near
    one-glyph-per-line output.
    """
    tamil_font = fitz.Font(fontfile=tamil_font_path)
    fallback_font = fitz.Font(fontfile=fallback_font_path)
    logo_bytes = LOGO_PATH.read_bytes() if (styled and LOGO_PATH.exists()) else None

    state = {"page": None, "x": BODY_RECT.x0, "y": BODY_RECT.y0}

    def start_page() -> None:
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_font(fontname="Tamil", fontfile=tamil_font_path)
        page.insert_font(fontname="Fallback", fontfile=fallback_font_path)
        if styled:
            if logo_bytes:
                page.insert_image(LOGO_LEFT_RECT, stream=logo_bytes)
                page.insert_image(LOGO_RIGHT_RECT, stream=logo_bytes)
            if title:
                page.insert_textbox(
                    fitz.Rect(0, 36, PAGE_W, 60),
                    title,
                    fontname="Tamil",
                    fontsize=12,
                    align=fitz.TEXT_ALIGN_CENTER,
                )
            page.insert_text((MARGIN_L, FOOTER_Y), "Veda Study SSB", fontname="helv", fontsize=11)
            page_num = str(len(doc))
            num_width = fitz.get_text_length(page_num, fontname="helv", fontsize=11)
            page.insert_text(
                (PAGE_W - MARGIN_R - num_width, FOOTER_Y), page_num, fontname="helv", fontsize=11
            )
        state["page"] = page
        state["x"] = BODY_RECT.x0
        state["y"] = BODY_RECT.y0 + BODY_FONT_SIZE

    def newline() -> None:
        state["x"] = BODY_RECT.x0
        state["y"] += LINE_HEIGHT
        if state["y"] > BODY_RECT.y1:
            start_page()

    def base_font(ch: str) -> tuple[fitz.Font, str]:
        return (tamil_font, "Tamil") if tamil_font.has_glyph(ord(ch)) else (fallback_font, "Fallback")

    def base_advance(ch: str) -> float:
        font, _ = base_font(ch)
        return font.glyph_advance(ord(ch)) * BODY_FONT_SIZE

    start_page()
    for line in text.split("\n"):
        for token in _WORD_SPLIT_RE.split(line):
            if not token:
                continue
            is_space = token.strip() == ""
            if is_space and state["x"] == BODY_RECT.x0:
                continue  # no leading whitespace at the start of a (wrapped) line
            clusters = _clusters(token)
            width = sum(base_advance(base) for base, _ in clusters)
            if not is_space and state["x"] + width > BODY_RECT.x1 and state["x"] > BODY_RECT.x0:
                newline()
            page = state["page"]
            for base, marks in clusters:
                font, fontname = base_font(base)
                advance = font.glyph_advance(ord(base)) * BODY_FONT_SIZE
                x, y = state["x"], state["y"]
                page.insert_text((x, y), base, fontname=fontname, fontsize=BODY_FONT_SIZE)
                above = below = 0.0
                for mark in marks:
                    mark_advance = fallback_font.glyph_advance(ord(mark)) * MARK_FONT_SIZE
                    mark_x = x + (advance - mark_advance) / 2
                    if unicodedata.combining(mark) == 220:  # below
                        below += BODY_FONT_SIZE * 0.22
                        mark_y = y + below
                    else:  # above (230/232/234 -- our marks are all "above" besides 220)
                        above += BODY_FONT_SIZE * 0.38
                        mark_y = y - above
                    page.insert_text((mark_x, mark_y), mark, fontname="Fallback", fontsize=MARK_FONT_SIZE)
                state["x"] += advance
        newline()  # each source line is its own verse/paragraph -- always break


def render_pdf(text: str, output_path: Path) -> None:
    """Render `text` as a plain, unstyled PDF (no logo/header/footer)."""
    doc = fitz.open()
    _draw_body(
        doc, text, styled=False, title=None,
        tamil_font_path=str(_ensure_tamil_font()), fallback_font_path=_ensure_fallback_font(),
    )
    doc.save(str(output_path))
    doc.close()


def render_pdf_styled(text: str, output_path: Path, title: str | None = None) -> None:
    """Render `text` as a PDF matching the "Veda Study SSB" house style: logo in
    each top corner, a centered header title repeated on every page, a
    "Veda Study SSB <page>" footer, and body text laid out at the same margins
    and font scale as the reference document."""
    doc = fitz.open()
    _draw_body(
        doc, text, styled=True, title=title,
        tamil_font_path=str(_ensure_tamil_font()), fallback_font_path=_ensure_fallback_font(),
    )
    doc.save(str(output_path))
    doc.close()


# A family of stray Latin tokens (n, u, f, s, ñ, gṁ, ...) shows up at matching
# positions in *both* docs/NarayanaSuktam_Sanskrit.pdf's and docs/NarayanaSuktam.pdf's
# extracted text layers -- confirmed to trace back to the non-standard-font-cmap
# issue already documented above ("Caveat" in CLAUDE.md), not to a conversion
# gap. Diff lines containing one of these are bucketed separately so real
# mismatches aren't buried in this known, shared, unfixable-from-the-text-layer
# noise.
KNOWN_ARTIFACT_RE = re.compile(r"(?:^|(?<=[\s.,()]))(?:g?ṁ|[nufsñṅ])(?=[\s.,()]|$)")


def validate() -> None:
    """Diagnostic: run docs/NarayanaSuktam_Sanskrit.pdf through the full
    pipeline and diff the result against docs/NarayanaSuktam.pdf's own text
    (the one ground-truth pair available), reporting an overall similarity
    score and a sample of real (non-artifact) mismatches. Not a pass/fail gate
    -- CLAUDE.md already documents several intentionally-unmodeled phenomena."""
    import difflib

    src = strip_repeated_boilerplate(extract_devanagari_text("docs/NarayanaSuktam_Sanskrit.pdf"))
    ref = strip_repeated_boilerplate(extract_devanagari_text("docs/NarayanaSuktam.pdf"))
    ours = convert(src)

    # Character-level diff over the whole text, not line-by-line: our line
    # breaks and the reference's don't land in exactly the same places (extra
    # blank lines, different wrapping upstream), so treating a line as the unit
    # of comparison makes nearly every line count as a full mismatch even where
    # the content is almost identical. SequenceMatcher's longest-matching-block
    # algorithm on raw characters finds real alignment despite that.
    sm = difflib.SequenceMatcher(None, ours, ref, autojunk=False)
    print(f"Overall character-level similarity: {sm.ratio():.1%} ({len(ours)} vs {len(ref)} chars)")

    real_mismatches = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        a, b = ours[i1:i2], ref[j1:j2]
        if len(a) < 3 and len(b) < 3:
            continue  # single-char noise (spacing, one stray mark) -- not worth reporting
        if KNOWN_ARTIFACT_RE.search(a) or KNOWN_ARTIFACT_RE.search(b):
            continue
        real_mismatches.append((i1, a, b))

    print(f"Non-artifact mismatched spans (length >= 3 chars): {len(real_mismatches)}")
    for i, a, b in sorted(real_mismatches, key=lambda t: -max(len(t[1]), len(t[2])))[:15]:
        print(f"\n  around char {i}:")
        print(f"    ours: {a!r}")
        print(f"    ref:  {b!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Diff conversion of docs/NarayanaSuktam_Sanskrit.pdf against "
        "docs/NarayanaSuktam.pdf and report a similarity score (diagnostic only)",
    )
    args, _ = parser.parse_known_args()
    if args.validate:
        validate()
        return

    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("text", nargs="?", help="Accented Devanagari Sanskrit text")
    group.add_argument(
        "-f", "--file", help="Path to a .pdf or .txt file containing the Devanagari text"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Filename to write the result under output/ "
        "(default: <input file name>_tamil.txt, or sanskrit_to_tamil_output.txt for inline text)",
    )
    parser.add_argument(
        "--title", help="Header title (in Tamil) to repeat at the top of every PDF page"
    )
    parser.add_argument(
        "--plain-pdf",
        action="store_true",
        help="Write a plain, unstyled PDF (no logo/header/footer) instead of the "
        "'Veda Study SSB' house style",
    )
    args = parser.parse_args()

    source = args.text
    if args.file:
        source = strip_repeated_boilerplate(extract_devanagari_text(args.file))

    result = convert(source)
    print(result)

    if args.output:
        stem = Path(args.output).stem
    elif args.file:
        stem = f"{Path(args.file).stem}_tamil"
    else:
        stem = "sanskrit_to_tamil_output"

    txt_path = resolve_output_path(f"{stem}.txt")
    txt_path.write_text(result + "\n", encoding="utf-8")
    print(f"Wrote {txt_path}", file=sys.stderr)

    pdf_path = resolve_output_path(f"{stem}.pdf")
    if args.plain_pdf:
        render_pdf(result, pdf_path)
    else:
        render_pdf_styled(result, pdf_path, title=args.title)
    print(f"Wrote {pdf_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
