#!/usr/bin/env python3
"""Classify Latin transliteration syllables by Sanskrit consonant aspiration/voicing.

Rule (Sanskrit Siksha varga classification):
  - No 'h' in the term            -> alpaprana (unaspirated)              -> 3
  - Has 'h', base consonant voiced (g, j, d, d-dot, b)   -> mahaprana, voiced   -> 4
  - Has 'h', base consonant unvoiced (k, c, t, t-dot, p) -> mahaprana, unvoiced -> 2

"base consonant" is the term's first letter, e.g. "bha" -> 'b', "kha" -> 'k'.
"""

import argparse
import sys
from pathlib import Path

from extract_transliterations import extract_text, find_transliterations, resolve_output_path

VOICED_UNASPIRATED = set("gjḍdb")
UNVOICED_UNASPIRATED = set("kcṭtp")


def classify_term(term: str) -> int:
    base = term[0].lower()
    has_h = "h" in term[1:].lower()
    if not has_h:
        return 3
    if base in VOICED_UNASPIRATED:
        return 4
    if base in UNVOICED_UNASPIRATED:
        return 2
    raise ValueError(f"Cannot classify term {term!r}: unrecognized base consonant {base!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", help="Path to the source PDF file")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Also replace every (term) occurrence in the document text with its number",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Filename to write the replaced text under output/ (default: <pdf name>_replaced.txt)",
    )
    args = parser.parse_args()

    text = extract_text(args.pdf_path)
    terms = sorted(find_transliterations(text))
    mapping = {term: classify_term(term) for term in terms}
    pdf_stem = Path(args.pdf_path).stem

    for term, number in mapping.items():
        print(f"{term}\t{number}")
    print(f"\n{len(mapping)} unique term(s) classified.", file=sys.stderr)

    mapping_path = resolve_output_path(f"{pdf_stem}_mapping.txt")
    mapping_path.write_text(
        "\n".join(f"{term}\t{number}" for term, number in mapping.items()) + "\n", encoding="utf-8"
    )
    print(f"Wrote {mapping_path}", file=sys.stderr)

    if args.replace:
        replaced = text
        for term, number in mapping.items():
            replaced = replaced.replace(f"({term})", str(number))
        output_name = args.output or f"{pdf_stem}_replaced.txt"
        output_path = resolve_output_path(output_name)
        output_path.write_text(replaced, encoding="utf-8")
        print(f"Wrote {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
