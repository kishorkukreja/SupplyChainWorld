#!/usr/bin/env python3
"""Capture actual command output and render it with local Chromium.

Usage: python scripts/capture_evidence.py LABEL -- COMMAND [ARG ...]
Run from the repository root. Only use commands with public, sanitized output.
The PNG is a screenshot of a labeled evidence report, not a product UI.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone


def main() -> int:
    if len(sys.argv) < 4 or sys.argv[2] != "--":
        raise SystemExit(__doc__)
    label = sys.argv[1]
    if not re.fullmatch(r"[a-z0-9-]+", label):
        raise SystemExit("LABEL must contain lowercase letters, digits and hyphens")
    root = Path(__file__).resolve().parents[1]
    destination = root / "evidence"
    destination.mkdir(exist_ok=True)
    (destination / "screenshots").mkdir(exist_ok=True)
    command = sys.argv[3:]
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True)
    output = completed.stdout + completed.stderr
    (destination / f"{label}.log").write_text(output)
    metadata = {
        "label": label, "captured_at": datetime.now(timezone.utc).isoformat(),
        "command": command, "cwd": str(root), "exit_code": completed.returncode,
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
        "capture_kind": "Chromium screenshot of command evidence report",
    }
    (destination / f"{label}.json").write_text(json.dumps(metadata, indent=2) + "\n")
    report = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>SupplyChainWorld evidence — {html.escape(label)}</title>
<style>body{{margin:40px;background:#f3f6fa;color:#102339;font:17px system-ui}}h1{{font-size:28px}}pre{{background:#102339;color:#edf4ff;padding:24px;white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 monospace}}.meta{{line-height:1.7}}code{{font-family:monospace}}</style>
<h1>SupplyChainWorld — {html.escape(label)}</h1>
<p>Actual command evidence report. This screenshot shows captured output, not a product interface.</p>
<div class="meta">UTC: {html.escape(metadata['captured_at'])}<br>
Command: <code>{html.escape(shlex.join(command))}</code><br>
Exit code: <strong>{completed.returncode}</strong><br>
Output SHA-256: <code>{metadata['output_sha256']}</code></div>
<pre>{html.escape(output)}</pre></html>'''
    report_path = destination / f"{label}.html"
    report_path.write_text(report)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path="/usr/bin/chromium", headless=True,
            args=["--no-sandbox", "--disable-crash-reporter", "--disable-breakpad", "--disable-crashpad-for-testing"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.set_content(report_path.read_text(), wait_until="load")
        page.screenshot(path=str(destination / "screenshots" / f"{label}.png"), full_page=True)
        browser.close()
    reports = sorted(destination.glob("*.html"))
    links = "".join(f'<li><a href="{p.name}">{p.stem}</a> · <a href="screenshots/{p.stem}.png">screenshot</a></li>' for p in reports if p.name != "index.html")
    (destination / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>SupplyChainWorld evidence</title><h1>SupplyChainWorld evidence</h1><p>Rendered command reports with raw logs and metadata beside each report. These are execution evidence screenshots, not UI screenshots or practitioner signoff.</p><ul>' + links + '</ul>')
    print(json.dumps(metadata, indent=2))
    print(f"Screenshot: evidence/screenshots/{label}.png")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
