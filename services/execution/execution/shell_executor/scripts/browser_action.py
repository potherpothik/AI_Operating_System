#!/usr/bin/env python3
"""
Phase 29: real headless-browser page reads for Testing Agent — genuine
Playwright automation (a real Chromium process, a real page load), never
a guess about what a page "probably" renders. Feeds real browser testing
of AIOS's own web UI (Control UI, Phase 24).

Deliberately read-only: this script only ever navigates and reads —
title, visible text, and a real screenshot file written to disk. No
click/fill/submit actions exist here at all; any interaction beyond
reading is explicitly out of this phase's scope (forward-plan doc,
Phase 29 scope: "read/screenshot-first, gated like every other mutating
tool for any interaction beyond reading").

The URL-scope restriction (internal AIOS targets only, never an
arbitrary external address) is enforced by the CALLER
(agents/reasoning_engine/browser_bridge.py) BEFORE this script is ever
invoked — this script itself has no network-scope opinion, the same
"the gate is upstream, not duplicated here" posture testing.run_suite's
own environment-verification split already established.

Usage: browser_action.py <url> <screenshot_output_path>
Prints a structured JSON summary on success, {"error": "..."} with exit 1 on failure.
"""
import json
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(json.dumps({"error": "playwright not installed — run: pip install playwright && playwright install chromium"}))
    sys.exit(1)


def browse(url: str, screenshot_path: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            response = page.goto(url, timeout=15000, wait_until="load")
            title = page.title()
            text = page.inner_text("body")[:5000]
            page.screenshot(path=screenshot_path)
            return {
                "url": url,
                "status_code": response.status if response else None,
                "title": title,
                "text": text,
                "screenshot_path": screenshot_path,
            }
        finally:
            browser.close()


def main():
    if len(sys.argv) != 3:
        print(json.dumps({"error": "usage: browser_action.py <url> <screenshot_output_path>"}))
        sys.exit(1)
    url, screenshot_path = sys.argv[1], sys.argv[2]
    try:
        result = browse(url, screenshot_path)
    except Exception as e:  # noqa: BLE001 — any real Playwright/navigation failure, reported honestly, never a fabricated page
        print(json.dumps({"error": f"browser navigation failed: {e}"}))
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
