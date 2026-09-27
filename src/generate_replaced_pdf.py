#!/usr/bin/env python3
"""Produce a PDF that mirrors the source PDF but with each (term) replaced by its number.

Every parenthesized Latin transliteration term (e.g. "(bha)") is located precisely on
the page (merging text spans split across fonts, which happens when a diacritic letter
falls back to a different font) and replaced by its classification number in the same
color. Since the digit is narrower than the term it replaces, the rest of that row is
shifted left to close the gap -- so the output keeps the original document's layout
and pattern without awkward holes in the text.
"""

import argparse
import re
import sys
from pathlib import Path

import fitz

from extract_transliterations import extract_text, find_transliterations, resolve_output_path
from classify_transliterations import classify_term

PAREN_RE = re.compile(r"\(([^)]*)\)")


def color_int_to_rgb(color: int) -> tuple[float, float, float]:
    r = ((color >> 16) & 255) / 255
    g = ((color >> 8) & 255) / 255
    b = (color & 255) / 255
    return (r, g, b)


def find_term_placements(page, mapping: dict[str, int]):
    """Yield (rect, number, size, color) for each mapped term found on the page."""
    page_dict = page.get_text("dict")
    for block in page_dict["blocks"]:
        for line in block.get("lines", []):
            spans = line["spans"]
            texts = [s["text"] for s in spans]
            full_line = "".join(texts)

            offsets = []
            pos = 0
            for t in texts:
                offsets.append((pos, pos + len(t)))
                pos += len(t)

            for m in PAREN_RE.finditer(full_line):
                term = m.group(1)
                if term not in mapping:
                    continue
                start, end = m.start(), m.end()
                involved_idx = [
                    i for i, (s, e) in enumerate(offsets) if e > start and s < end
                ]
                if not involved_idx:
                    continue
                involved = [spans[i] for i in involved_idx]
                erase_rect = fitz.Rect(involved[0]["bbox"])
                for sp in involved[1:]:
                    erase_rect |= fitz.Rect(sp["bbox"])

                # Size the replacement digit like the base Tamil character it
                # annotates (the span immediately before the term), not the small
                # annotation font itself -- but keep the vertical position of the
                # original (term) annotation's own bbox, which already sits raised
                # above the main baseline, so the digit reads as a superscript
                # instead of an inline character.
                first_idx = involved_idx[0]
                if first_idx > 0:
                    base_size = spans[first_idx - 1]["size"]
                else:
                    base_size = involved[0]["size"]
                baseline_y = erase_rect.y1

                digit_text = str(mapping[term])
                # Left-align to where the annotation started, rather than centering
                # over its full width, so the digit reads as a superscript sitting
                # to the right of the base character (top-right), not centered atop it.
                anchor = fitz.Point(erase_rect.x0, baseline_y)

                yield erase_rect, anchor, digit_text, base_size, involved[0]["color"]


# Small breathing room left between a replacement digit and the text that follows it.
DIGIT_PADDING = 0.5


def group_rows(page) -> list[fitz.Rect]:
    """Return one bbox per visual text row, top to bottom.

    get_text("dict") sometimes splits one visual row into several "lines" (e.g.
    around an inline image), so lines whose vertical extents overlap are merged --
    all pieces of a row must shift together.
    """
    rects = [
        fitz.Rect(line["bbox"])
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        if line["dir"] == (1.0, 0.0) and not fitz.Rect(line["bbox"]).is_empty
    ]
    rects.sort(key=lambda r: r.y0)
    rows: list[fitz.Rect] = []
    for r in rects:
        if rows and r.y0 < rows[-1].y1 - 1:
            rows[-1] |= r
        else:
            rows.append(fitz.Rect(r))
    return rows


def row_band(rows: list[fitz.Rect], i: int, page_rect: fitz.Rect) -> tuple[float, float]:
    """Vertical band owned by rows[i]: halfway to its neighbors, so no ink is lost."""
    top = page_rect.y0 if i == 0 else (rows[i - 1].y1 + rows[i].y0) / 2
    bottom = page_rect.y1 if i == len(rows) - 1 else (rows[i].y1 + rows[i + 1].y0) / 2
    return top, bottom


def build_replaced_pdf(pdf_path: str) -> fitz.Document:
    """Build the replaced PDF, closing up the space each shorter digit leaves behind.

    Each output page is composed from clipped slices of the (unmodified) source page
    via show_pdf_page(), which keeps text as vector/selectable and carries Vedic accent
    marks, inline images, and fonts along untouched. Rows without terms are copied
    as-is; in a row containing terms, the source is cut at each (term) and every slice
    after it is drawn shifted left by the width saved so far, with the digit drawn in
    the term's place. Nothing is redacted: the (term) itself is simply never copied.
    """
    src = fitz.open(pdf_path)
    text = extract_text(pdf_path)
    terms = sorted(find_transliterations(text))
    mapping = {term: classify_term(term) for term in terms}

    out = fitz.open()
    for src_page in src:
        page_rect = src_page.rect
        page = out.new_page(width=page_rect.width, height=page_rect.height)

        def copy(clip: fitz.Rect, dx: float = 0.0) -> None:
            clip = clip & page_rect
            if clip.is_empty:
                return
            page.show_pdf_page(clip + (-dx, 0, -dx, 0), src, src_page.number, clip=clip)

        placements = list(find_term_placements(src_page, mapping))
        rows = group_rows(src_page)
        # Map each placement to the row containing its vertical center.
        by_row: dict[int, list] = {}
        for pl in placements:
            cy = (pl[0].y0 + pl[0].y1) / 2
            for i, r in enumerate(rows):
                if r.y0 <= cy <= r.y1:
                    by_row.setdefault(i, []).append(pl)
                    break

        cursor_y = page_rect.y0
        digits = []
        for i in sorted(by_row):
            top, bottom = row_band(rows, i, page_rect)
            copy(fitz.Rect(page_rect.x0, cursor_y, page_rect.x1, top))
            cursor_y = bottom

            shift = 0.0
            seg_x0 = page_rect.x0
            for erase_rect, anchor, digit_text, size, color in sorted(
                by_row[i], key=lambda pl: pl[0].x0
            ):
                copy(fitz.Rect(seg_x0, top, erase_rect.x0, bottom), shift)
                digit_x = erase_rect.x0 - shift
                digits.append((fitz.Point(digit_x, anchor.y), digit_text, size, color))
                digit_w = fitz.get_text_length(digit_text, fontname="helv", fontsize=size)
                shift += erase_rect.width - digit_w - DIGIT_PADDING
                # Zero-advance Vedic accent marks placed right after a term draw their
                # ink leftward, over the term's ")" -- keep any ink above/below the
                # term's own box, moving it with the text that follows.
                copy(fitz.Rect(erase_rect.x0, top, erase_rect.x1, erase_rect.y0), shift)
                copy(fitz.Rect(erase_rect.x0, erase_rect.y1, erase_rect.x1, bottom), shift)
                seg_x0 = erase_rect.x1
            # The rest of the row's text shifts; anything beyond it (e.g. a corner
            # logo sharing the row) stays put.
            row_x1 = rows[i].x1
            copy(fitz.Rect(seg_x0, top, row_x1, bottom), shift)
            copy(fitz.Rect(row_x1, top, page_rect.x1, bottom))
        copy(fitz.Rect(page_rect.x0, cursor_y, page_rect.x1, page_rect.y1))

        for anchor, digit_text, size, color in digits:
            page.insert_text(
                anchor,
                digit_text,
                fontname="helv",
                fontsize=size,
                color=color_int_to_rgb(color),
            )

    src.close()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", help="Path to the source PDF file")
    parser.add_argument(
        "-o",
        "--output",
        help="Filename to write the replaced PDF under output/ (default: <pdf name>_replaced.pdf)",
    )
    args = parser.parse_args()

    doc = build_replaced_pdf(args.pdf_path)
    output_name = args.output or f"{Path(args.pdf_path).stem}_replaced.pdf"
    output_path = resolve_output_path(output_name)
    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()
    print(f"Wrote {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
