#!/usr/bin/env python3
"""Minimal, zero-dependency Markdown -> PDF writer.

Standard library only. No third-party packages, no network, no subprocess.
Renders a useful subset of Markdown well enough for research reports:

  # / ## / ### headings
  paragraphs with **bold**, *italic*, `inline code`
  > block quotes       - bullet lists        1. ordered lists
  ``` fenced code blocks
  | tables | with | header rows |
  --- horizontal rules
  --- separate YAML-free title blocks (ignored)

Text layout uses the real Helvetica AFM advance widths so wrapping and
table column sizing match what a PDF viewer will actually show, instead of
a monospace approximation.

Usage
-----
    python md2pdf.py REPORT.md                 # writes REPORT.pdf
    python md2pdf.py REPORT.md -o report.pdf
"""

from __future__ import annotations

import argparse
import re
import sys
import zlib

# ---------------------------------------------------------------- font widths

_HELV = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584,
    "?": 556, "@": 1015, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "{": 334, "|": 260, "}": 334, "~": 584,
    "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
    "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556,
    "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
    "0": 556, "1": 556, "2": 556, "3": 556, "4": 556, "5": 556, "6": 556,
    "7": 556, "8": 556, "9": 556,
}
_HELV_B = dict(_HELV)
_HELV_B.update({
    "!": 333, '"': 474, "&": 722, "'": 238, ":": 333, ";": 333, "?": 611,
    "@": 975, "[": 333, "]": 333, "^": 584, "{": 389, "|": 280, "}": 389,
    "A": 722, "C": 722, "E": 667, "J": 556, "K": 722, "L": 611, "N": 722,
    "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722, "V": 667,
    "Z": 611, "a": 556, "b": 611, "c": 556, "d": 611, "e": 556, "f": 333,
    "g": 611, "h": 611, "i": 278, "j": 278, "k": 556, "l": 278, "m": 889,
    "n": 611, "o": 611, "p": 611, "q": 611, "r": 389, "s": 556, "t": 333,
    "u": 611, "v": 556, "w": 778, "x": 556, "y": 556,
})

FONTS = {"regular": ("F1", _HELV), "bold": ("F2", _HELV_B),
         "italic": ("F3", _HELV), "mono": ("F4", None)}

# characters outside latin-1 that exist in WinAnsiEncoding
_WINANSI = {"\u20ac": 0x80, "\u201a": 0x82, "\u0192": 0x83, "\u201e": 0x84,
            "\u2026": 0x85, "\u2020": 0x86, "\u2021": 0x87, "\u02c6": 0x88,
            "\u2030": 0x89, "\u0160": 0x8a, "\u2039": 0x8b, "\u0152": 0x8c,
            "\u017d": 0x8e, "\u2018": 0x91, "\u2019": 0x92, "\u201c": 0x93,
            "\u201d": 0x94, "\u2022": 0x95, "\u2013": 0x96, "\u2014": 0x97,
            "\u02dc": 0x98, "\u2122": 0x99, "\u0161": 0x9a, "\u203a": 0x9b,
            "\u0153": 0x9c, "\u017e": 0x9e, "\u0178": 0x9f}
# characters we cannot encode -> safe ASCII substitutes
_SUBST = {"\u2212": "-", "\u2192": "->", "\u00a0": " ", "\u2265": ">=",
          "\u2264": "<=", "\u2248": "~=", "\u2500": "-", "\u2502": "|",
          "\u2190": "<-", "\u03b1": "alpha", "\u03b2": "beta", "\u03bb": "lambda"}


def sanitize(text: str) -> str:
    """Replace anything a core-14 WinAnsi font cannot render."""
    out = []
    for ch in text:
        code = ord(ch)
        if ch in _SUBST:
            out.append(_SUBST[ch])
        elif code < 256 or ch in _WINANSI:
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


def pdf_escape(text: str) -> bytes:
    """Map text to PDF string bytes under WinAnsiEncoding."""
    res = bytearray()
    for ch in text:
        code = ord(ch)
        if code < 256:
            b = code
        elif ch in _WINANSI:
            b = _WINANSI[ch]
        else:
            b = 0x3F  # '?'
        if b in (0x28, 0x29, 0x5C):  # ( ) \
            res.append(0x5C)
        res.append(b)
    return bytes(res)


def text_width(text: str, style: str, size: float) -> float:
    _, table = FONTS[style]
    if table is None:  # Courier is monospaced: 600/1000 em
        return len(text) * 0.6 * size
    return sum(table.get(ch, 556) for ch in text) * size / 1000.0


# ------------------------------------------------------------------- inline

_INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|(?<!\*)\*[^*]+?\*(?!\*))")


def parse_inline(text: str):
    """Split a raw line into [(style, text), ...] runs."""
    runs, pos = [], 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            runs.append(("regular", text[pos:m.start()]))
        tok = m.group(0)
        if tok.startswith("**"):
            runs.append(("bold", tok[2:-2]))
        elif tok.startswith("`"):
            runs.append(("mono", tok[1:-1]))
        else:
            runs.append(("italic", tok[1:-1]))
        pos = m.end()
    if pos < len(text):
        runs.append(("regular", text[pos:]))
    return runs or [("regular", "")]


def wrap_runs(runs, width: float, size: float):
    """Greedy word wrap that preserves per-word inline styles."""
    words = []
    for style, chunk in runs:
        for piece in re.split(r"(\s+)", chunk):
            if piece:
                words.append((style, piece))
    lines, current, cur_w = [], [], 0.0
    for style, word in words:
        if word.strip() == "":
            if current:
                current.append(("regular", " "))
            continue
        w = text_width(word, style, size)
        if current and cur_w + w > width:
            lines.append(current)
            current, cur_w = [], 0.0
        current.append((style, word))
        cur_w += w + text_width(" ", style, size)
    if current:
        lines.append(current)
    return lines or [[("", "regular")]]


def draw_runs(stream, runs, size: float):
    parts = []
    for style, txt in runs:
        if txt == "":
            continue
        name, _ = FONTS.get(style, FONTS["regular"])
        parts.append(b"/" + name.encode() + b" " + f"{size:g}".encode()
                     + b" Tf (" + pdf_escape(txt) + b") Tj")
    if parts:
        stream.extend(parts)


# ------------------------------------------------------------------- writer

PAGE_W, PAGE_H = 595.28, 841.89  # A4 portrait, points
MARGIN_X, MARGIN_TOP, MARGIN_BOT = 56.0, 60.0, 56.0
BODY_W = PAGE_W - 2 * MARGIN_X


class PdfDoc:
    def __init__(self):
        self.pages = []
        self.stream = []
        self.y = PAGE_H - MARGIN_TOP

    # -- page handling
    def new_page(self):
        if self.stream:
            self.pages.append(self.stream)
        self.stream = []
        self.y = PAGE_H - MARGIN_TOP

    def need(self, height: float):
        if self.y - height < MARGIN_BOT:
            self.new_page()
            return True
        return False

    # -- primitives
    def _text_at(self, x, y, style, size, txt):
        name, _ = FONTS.get(style, FONTS["regular"])
        self.stream.append(
            b"BT /" + name.encode() + b" " + f"{size:g}".encode() + b" Tf 1 0 0 1 "
            + f"{x:.2f} {y:.2f}".encode() + b" Tm (" + pdf_escape(txt) + b") Tj ET")

    def _runs_at(self, x, y, runs, size):
        self.stream.append(b"BT 1 0 0 1 " + f"{x:.2f} {y:.2f}".encode() + b" Tm ")
        draw_runs(self.stream, runs, size)
        self.stream.append(b"ET")

    def _line(self, x1, y1, x2, y2, w=0.6, gray=0.65):
        self.stream.append(
            f"{gray:g} G {w:g} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S".encode())

    def _rect(self, x, y, w, h, gray=0.94):
        self.stream.append(
            f"{gray:g} g {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f".encode())

    # -- blocks
    def heading(self, text, level):
        size, space_before = {1: (19.0, 22.0), 2: (14.5, 17.0),
                              3: (12.0, 13.0)}.get(level, (11.0, 11.0))
        space_after = size * 0.55
        self.need(size + space_before)
        self.y -= space_before
        for line in wrap_runs(parse_inline(text), BODY_W, size):
            self._runs_at(MARGIN_X, self.y - size, line, size)
            self.y -= size * 1.28
        self.y -= space_after - size * 0.28
        if level <= 2:
            self._line(MARGIN_X, self.y + space_after * 0.55,
                       PAGE_W - MARGIN_X, self.y + space_after * 0.55, 0.5, 0.80)

    def paragraph(self, text):
        size, lead = 10.0, 14.0
        lines = wrap_runs(parse_inline(text), BODY_W, size)
        self.need(len(lines) * lead)
        for line in lines:
            self._runs_at(MARGIN_X, self.y - size, line, size)
            self.y -= lead
        self.y -= 3.0

    def quote(self, text):
        size, lead = 10.0, 14.0
        lines = wrap_runs(parse_inline(text), BODY_W - 18, size)
        height = len(lines) * lead + 6
        self.need(height)
        top = self.y
        self._rect(MARGIN_X, top - height, 3.0, height, 0.75)
        yy = top - 3 - size
        for line in lines:
            self._runs_at(MARGIN_X + 12, yy, line, size)
            yy -= lead
        self.y = top - height - 6.0

    def bullet(self, text, ordered=False, index=1):
        size, lead = 10.0, 13.5
        marker = f"{index}. " if ordered else "\u2022 "
        lines = wrap_runs(parse_inline(text), BODY_W - 20, size)
        self.need(len(lines) * lead)
        first = True
        for line in lines:
            x = MARGIN_X + (0 if not first else 14)
            if first:
                self._text_at(MARGIN_X, self.y - size, "bold", size, marker)
            self._runs_at(MARGIN_X + 14, self.y - size, line, size)
            self.y -= lead
            first = False
        self.y -= 1.5

    def code_block(self, lines):
        size, lead = 8.6, 11.2
        height = len(lines) * lead + 12
        if height > PAGE_H - MARGIN_TOP - MARGIN_BOT:  # split long blocks
            for chunk_start in range(0, len(lines), 40):
                self.code_block(lines[chunk_start:chunk_start + 40])
            return
        self.need(height)
        top = self.y
        self._rect(MARGIN_X, top - height, BODY_W, height, 0.945)
        self._line(MARGIN_X, top, MARGIN_X, top - height, 0.5, 0.80)
        yy = top - 6 - size
        for raw in lines:
            if yy - size < MARGIN_BOT:
                break
            self._text_at(MARGIN_X + 8, yy, "mono", size, raw)
            yy -= lead
        self.y = top - height - 4.0

    def table(self, rows):
        size, lead = 9.2, 12.6
        cols = max(len(r) for r in rows)
        if cols == 0:
            return
        widths = [0.0] * cols
        for r in rows:
            for i, cell in enumerate(r):
                widths[i] = max(widths[i], text_width(cell, "bold", size) + 12)
        total = sum(widths)
        if total > BODY_W:
            widths = [w * BODY_W / total for w in widths]
        height = len(rows) * lead + 8
        self.need(height)
        top = self.y
        yy = top - 4
        for ridx, row in enumerate(rows):
            x = MARGIN_X
            for i in range(cols):
                cell = row[i] if i < len(row) else ""
                style = "bold" if ridx == 0 else "regular"
                txt = cell
                while text_width(txt, style, size) > widths[i] - 8 and len(txt) > 2:
                    txt = txt[:-1]
                if txt != cell:
                    txt = txt[:-1] + "\u2026" if len(txt) > 3 else txt
                self._text_at(x + 4, yy - size, style, size, txt)
                x += widths[i]
            yy -= lead
            if ridx == 0:
                self._line(MARGIN_X, yy + 3, MARGIN_X + sum(widths), yy + 3, 0.5, 0.55)
        self._line(MARGIN_X, yy + 6, MARGIN_X + sum(widths), yy + 6, 0.4, 0.80)
        self.y = yy - 6.0

    def rule(self):
        self.need(12)
        self.y -= 6
        self._line(MARGIN_X, self.y, PAGE_W - MARGIN_X, self.y, 0.5, 0.82)
        self.y -= 8

    # -- assembly
    def build(self, title="Report"):
        if self.stream:
            self.pages.append(self.stream)
        total = len(self.pages)
        objects = []          # list of raw object bytes (1-indexed later)

        font_res = (b"<< /Font << /F1 " + b"5 0 R /F2 6 0 R /F3 7 0 R /F4 8 0 R >> >>")

        page_ids = [9 + 2 * i for i in range(total)]
        kids = b" ".join(f"{pid} 0 R".encode() for pid in page_ids)

        # 1 catalog
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        # 2 pages
        objects.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count "
                       + str(total).encode() + b" >>")
        # 3 info
        objects.append(b"<< /Title (" + pdf_escape(title) + b") /Producer (md2pdf.py) >>")
        # 4 unused placeholder to keep numbering stable
        objects.append(b"<< >>")
        # 5-8 fonts
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")

        i = 0
        for pid in page_ids:
            content_id = pid + 1
            objects.append(
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
                + f"{PAGE_W:.2f} {PAGE_H:.2f}".encode() + b"] /Resources " + font_res
                + b" /Contents " + f"{content_id} 0 R".encode() + b" >>")

            ops = list(self.pages[i])
            # footer page number
            footer = b"BT /F1 8 Tf 0.45 G 1 0 0 1 " + (
                f"{PAGE_W/2 - 12:.2f} {MARGIN_BOT/2:.2f}".encode()
            ) + b" Tm (" + pdf_escape(f"{i+1} / {total}") + b") Tj ET"
            ops.append(footer)
            payload = b"\n".join(ops)
            compressed = zlib.compress(payload, 9)
            objects.append(
                b"<< /Length " + str(len(compressed)).encode()
                + b" /Filter /FlateDecode >>\nstream\n" + compressed + b"\nendstream")
            i += 1

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for idx, obj in enumerate(objects, start=1):
            offsets.append(len(out))
            out += str(idx).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
        xref_at = len(out)
        n = len(objects) + 1
        out += b"xref\n0 " + str(n).encode() + b"\n"
        out += b"0000000000 65535 f \n"
        for off in offsets[1:]:
            out += f"{off:010d} 00000 n \n".encode()
        out += b"trailer\n<< /Size " + str(n).encode() + b" /Root 1 0 R /Info 3 0 R >>\n"
        out += b"startxref\n" + str(xref_at).encode() + b"\n%%EOF\n"
        return bytes(out)


# ---------------------------------------------------------------- parser

def render_markdown(md: str, doc: PdfDoc):
    lines = md.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)
    in_code = False
    code_buf = []
    while i < n:
        raw = lines[i].rstrip()
        line = sanitize(raw)
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                doc.code_block(code_buf)
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line if line.strip() else "")
            i += 1
            continue

        if stripped.startswith("---") and set(stripped) <= set("-"):
            doc.rule()
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = min(len(m.group(1)), 3)
            doc.heading(m.group(2).strip(), level)
            i += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 3:
            block = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in sanitize(lines[i].strip()).strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells if c):
                    block.append(cells)
                i += 1
            if block:
                doc.table(block)
            continue

        if stripped.startswith(">"):
            block = []
            while i < n and lines[i].strip().startswith(">"):
                block.append(sanitize(lines[i].strip().lstrip(">").strip()))
                i += 1
            doc.quote(" ".join(x for x in block if x))
            continue

        m = re.match(r"^[-*]\s+(.*)$", stripped)
        if m:
            doc.bullet(m.group(1).strip())
            i += 1
            continue
        m = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if m:
            doc.bullet(m.group(2).strip(), ordered=True, index=int(m.group(1)))
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        # paragraph: join consecutive non-blank, non-special lines
        buf = [stripped]
        i += 1
        while i < n:
            nxt = sanitize(lines[i]).strip()
            if (not nxt or nxt.startswith(("#", ">", "|", "```", "---"))
                    or re.match(r"^([-*]\s|\d+\.\s)", nxt)):
                break
            buf.append(nxt)
            i += 1
        doc.paragraph(" ".join(buf))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Zero-dependency Markdown -> PDF.")
    ap.add_argument("markdown", help="Input .md file")
    ap.add_argument("-o", "--output", default=None, help="Output .pdf path")
    args = ap.parse_args(argv)

    with open(args.markdown, encoding="utf-8") as fh:
        md = fh.read()

    doc = PdfDoc()
    doc.new_page()
    render_markdown(md, doc)
    out_path = args.output or (args.markdown.rsplit(".", 1)[0] + ".pdf")
    data = doc.build(title=sanitize(md.split("\n")[0].lstrip("# ").strip()))
    with open(out_path, "wb") as fh:
        fh.write(data)
    print(f"wrote {out_path} ({len(data)} bytes, {len(doc.pages)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
