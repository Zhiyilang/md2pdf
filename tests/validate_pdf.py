#!/usr/bin/env python3
"""Structural validator for PDFs produced by md2pdf.py.

Standard library only. Exits non-zero on the first structural problem, so it can
be used as a CI gate.

Checks performed
----------------
1.  %PDF header and %%EOF trailer are present.
2.  startxref points at an xref table, whose declared Size matches the number of
    written entries, and entry 0 is the free object.
3.  Every non-free xref byte offset actually lands on "<n> 0 obj".
4.  Every content stream decompresses under zlib /FlateDecode.
5.  Every text placement lies inside the A4 page box, with a small tolerance.
6.  No filled rectangle has a negative width or height.

Usage
-----
    python3 tests/validate_pdf.py out.pdf
"""

import re
import sys
import zlib

PAGE_W, PAGE_H = 595.28, 841.89
TOLERANCE = 4.0


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main(argv):
    if len(argv) != 2:
        print("usage: validate_pdf.py <file.pdf>")
        return 2
    path = argv[1]
    with open(path, "rb") as fh:
        raw = fh.read()

    if not raw.startswith(b"%PDF-"):
        fail("missing %PDF header")
    if not raw.rstrip().endswith(b"%%EOF"):
        fail("missing %%EOF trailer")

    m = re.search(rb"startxref\s+(\d+)\s+%%EOF", raw)
    if not m:
        fail("missing startxref")
    xref_at = int(m.group(1))
    if raw[xref_at:xref_at + 4] != b"xref":
        fail(f"startxref {xref_at} does not point at the xref table")

    tail = raw[xref_at:]
    xm = re.match(rb"xref\s+0\s+(\d+)\s+", tail)
    if not xm:
        fail("malformed xref header")
    declared = int(xm.group(1))
    entries = re.findall(rb"(\d{10}) (\d{5}) ([nf])", tail)
    if len(entries) != declared:
        fail(f"Size says {declared} but {len(entries)} entries were written")
    if entries[0][2] != b"f":
        fail("entry 0 is not the free object")

    for idx, (off, _gen, typ) in enumerate(entries):
        if typ == b"f":
            continue
        start = int(off)
        expect = f"{idx} 0 obj".encode()
        if not raw[start:start + len(expect)].startswith(expect):
            fail(f"xref entry {idx} points at {raw[start:start + 20]!r}")

    streams = re.findall(
        rb"<< /Length \d+ /Filter /FlateDecode >>\nstream\n(.*?)\nendstream",
        raw, re.S)
    if not streams:
        fail("no content streams found")

    body = b""
    for s in streams:
        try:
            body += zlib.decompress(s)
        except zlib.error as exc:
            fail(f"stream decompression failed: {exc}")

    if len(streams) < 1:
        fail("document has no pages")

    coords = re.findall(rb"1 0 0 1 ([-\d.]+) ([-\d.]+) Tm", body)
    if not coords:
        fail("no text was drawn")
    for xs, ys in coords:
        x, y = float(xs), float(ys)
        if not (0 <= x <= PAGE_W) or not (0 <= y <= PAGE_H):
            fail(f"text placed outside the page at ({x}, {y})")

    for rect in re.findall(rb"([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+) re f", body):
        _x, _y, w, h = (float(v) for v in rect)
        if w <= 0 or h <= 0:
            fail(f"rectangle with non-positive extent: w={w} h={h}")

    drawn = re.findall(rb"\((.*?)\) Tj", body)
    real = [d for d in drawn if len(d) > 1]
    if not real:
        fail("no non-trivial strings were drawn")

    print(f"OK  pages={len(streams)} placements={len(coords)} "
          f"strings={len(drawn)} ({len(real)} non-trivial) bytes={len(raw)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
