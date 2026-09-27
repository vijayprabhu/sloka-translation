#!/usr/bin/env python3
"""Extract unique Latin transliteration syllables enclosed in parentheses from a PDF.

Source PDFs interleave native-script characters with their Latin transliteration
in parentheses, e.g. "க(ga)ணபத்(d)ய". This script pulls out every parenthesized
group, keeps only the ones made of Latin letters (including accented/diacritic
forms such as ā, ī, ū, ṭ, ḍ, ś), and reports the unique set found.
"""

import argparse
import fitz
import re
import sys
import unicodedata
from pathlib import Path

PAREN_GROUP_RE = re.compile(r"\(([^)]*)\)")

# Latin letters plus combining diacritical marks used by IAST-style transliteration.
LATIN_TERM_RE = re.compile(r"^[A-Za-z̀-ͯḀ-ỿÀ-ɏ]+$")

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def resolve_output_path(filename: str) -> Path:
    """Return a path for `filename` inside the project's output/ folder, creating it if needed."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / Path(filename).name


def extract_text(pdf_path: str) -> str:
    with fitz.open(pdf_path) as doc:
        return "".join(page.get_text() for page in doc)


def is_latin_term(term: str) -> bool:
    return bool(term) and bool(LATIN_TERM_RE.match(term))


def find_transliterations(text: str) -> set[str]:
    groups = PAREN_GROUP_RE.findall(text)
    return {g for g in groups if is_latin_term(g)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", help="Path to the source PDF file")
    parser.add_argument(
        "-o",
        "--output",
        help="Filename to write the results under output/ (default: <pdf name>_terms.txt)",
    )
    args = parser.parse_args()

    text = extract_text(args.pdf_path)
    terms = sorted(find_transliterations(text), key=lambda s: (unicodedata.normalize("NFKD", s), s))

    for term in terms:
        print(term)
    print(f"\n{len(terms)} unique transliteration(s) found.", file=sys.stderr)

    output_name = args.output or f"{Path(args.pdf_path).stem}_terms.txt"
    output_path = resolve_output_path(output_name)
    output_path.write_text("\n".join(terms) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
