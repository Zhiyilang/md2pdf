# md2pdf

[![verify](https://github.com/Zhiyilang/md2pdf/actions/workflows/verify.yml/badge.svg)](https://github.com/Zhiyilang/md2pdf/actions/workflows/verify.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Turn a Markdown file into a real PDF. Zero dependencies. No pandoc, no LaTeX, no `pip install`.**

Python standard library only. A single ~450-line file that writes a valid
PDF 1.4 document directly — no third-party renderer, no network, no subprocess.

## Why this exists

Most "Markdown to PDF" toolchains drag in a Node toolchain, LaTeX, a headless
browser, or a heavy wheel. This one needs nothing but `python3`. It exists because
hackathon and grant submissions ask for **a PDF specifically**, and reportlab /
pandoc are not always installable on a locked-down machine.

## Usage

```bash
python3 md2pdf.py REPORT.md              # writes REPORT.pdf next to the source
python3 md2pdf.py REPORT.md -o paper.pdf # explicit output path
```

## Supported Markdown

| Element | Syntax | Notes |
|---|---|---|
| Headings | `#`, `##`, `###` | sizes 19 / 14.5 / 12 pt, rule under H1–H2 |
| Paragraphs | plain text | soft-wrapped; consecutive lines joined |
| Emphasis | `**bold**`, `*italic*`, `` `code` `` | mixed inline runs supported |
| Block quotes | `> quote` | grey rule bar + inset text |
| Lists | `- item`, `1. item` | bullets and ordered numbering |
| Code blocks | ```` ``` ```` fences | monospace on a shaded panel |
| Tables | `| a | b |` | header row bolded, columns auto-sized |
| Horizontal rule | `---` | full-width hairline |

Page size is A4 portrait with 56 pt side margins; every page gets a centred
`n / total` footer. Long code blocks split across pages instead of being clipped.

## Why the layout actually comes out right

Naive PDF writers approximate text width with a monospace ratio, which produces
wrapping that does not match the viewer. This module embeds the **real Helvetica
and Helvetica-Bold advance-width tables** (units per 1000 em) and computes line
breaks and table column widths from them, so what you measure is what gets drawn.

Text is emitted under `WinAnsiEncoding`. Characters that a core-14 font cannot
represent are mapped to safe ASCII substitutes (for example `−` to `-`, `→` to
`->`) rather than being silently dropped, and anything still unrenderable becomes
`?`. That substitution table is explicit in `md2pdf.py`, so nothing is hidden.

## Verifying the output

The file is plain enough to audit yourself:

```bash
python3 -c "import re,zlib,sys; raw=open('REPORT.pdf','rb').read(); \
 print('streams', len(re.findall(rb'/FlateDecode', raw)))"
```

A structural self-check (xref offsets point at their objects, all content streams
decompress, no text placement falls outside the page, no negative-size rectangle)
is what we ran against every generated report in this project.

## License

MIT. See [LICENSE](LICENSE).
