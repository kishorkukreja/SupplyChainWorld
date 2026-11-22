#!/usr/bin/env python3
"""Render an S01 `timeline.txt` (written by scripts/run_dynamic_demo*.py) as a plain `timeline.html` page.

The v0.1 demo already writes a timeline page; v0.2 to v0.4 write only the text file. This adds the same kind of
page for them without touching those scripts or their committed evidence.

Usage: python scripts/render_s01_timeline_html.py --timeline evidence/issue-36-v04/timeline.txt --out /tmp/timeline.html --title "S01 v0.4 timeline"
Deterministic: the page is the text, escaped, in a <pre>.
"""
import argparse
import html
from pathlib import Path


def render(text, title):
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<title>{html.escape(title)}</title><style>body{{font:14px/1.4 sans-serif;margin:24px}}'
            'pre{background:#f4f4f4;padding:10px;white-space:pre-wrap;font-size:12px}</style></head><body>'
            f'<h1>{html.escape(title)}</h1><pre id="timeline">{html.escape(text)}</pre></body></html>\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timeline', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--title', default='S01 timeline')
    args = ap.parse_args()
    Path(args.out).write_text(render(Path(args.timeline).read_text(), args.title))


if __name__ == '__main__':
    main()
