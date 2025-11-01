"""
Headless UI verification: Assert that the dashboard shows at least one sensor value
or the ONLINE badge within a configurable timeout.

Usage:
  python tools/ui_check.py --url http://192.168.88.49:8080/ --timeout 20

Exit codes:
  0 = success (value visible or ONLINE badge present)
  1 = failure (timed out)
  2 = other error
"""
from __future__ import annotations
import sys
import time
import argparse
from typing import Optional, Tuple
import re

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    print("ERROR: Playwright is not installed. pip install playwright && python -m playwright install chromium", file=sys.stderr)
    raise


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RDWC UI verification")
    p.add_argument("--url", default="http://localhost:8080/", help="Dashboard URL")
    p.add_argument("--timeout", type=int, default=20, help="Timeout seconds")
    p.add_argument("--headful", action="store_true", help="Run with a visible browser window")
    return p.parse_args(argv)


def is_value_text(s: Optional[str]) -> bool:
    if s is None:
        return False
    t = s.strip()
    if t == "--" or t == "—" or t == "":
        return False
    return True


def page_has_value_or_online(page) -> Tuple[bool, str]:
    """Return (ok, debug) whether the page shows a value or online badge."""
    # Check ONLINE badge via class
    try:
        badge = page.query_selector("#sensors-online.online")
        if badge is not None:
            return True, "badge=online"
    except Exception:
        pass

    # Read text contents of value spans (new sensors card)
    val_temp = page.text_content("#val-temp") if page.query_selector("#val-temp") else None
    val_ec   = page.text_content("#val-ec") if page.query_selector("#val-ec") else None
    val_ph   = page.text_content("#val-ph") if page.query_selector("#val-ph") else None

    any_value = any(is_value_text(x) for x in (val_temp, val_ec, val_ph))
    dbg = f"temp={val_temp!r} ec={val_ec!r} ph={val_ph!r}"

    # Broader fallback: look for any numeric-looking metric text under sensors card
    if not any_value:
        try:
            metrics = page.query_selector_all("#sensors-card .metric") or []
            texts = [m.text_content() for m in metrics]
            numericish = any((t and re.search(r"[0-9]", t)) for t in texts)
            if numericish:
                return True, f"metrics={texts}"
            # KPI fallback
            kpi_t = page.text_content("#kpiTemp") if page.query_selector("#kpiTemp") else None
            kpi_e = page.text_content("#kpiEc") if page.query_selector("#kpiEc") else None
            kpi_p = page.text_content("#kpiPh") if page.query_selector("#kpiPh") else None
            if any(is_value_text(x) for x in (kpi_t, kpi_e, kpi_p)):
                return True, f"kpi temp={kpi_t!r} ec={kpi_e!r} ph={kpi_p!r}"
        except Exception:
            pass
    return any_value, dbg


def main(argv=None) -> int:
    args = parse_args(argv)
    deadline = time.time() + max(1, args.timeout)

    with sync_playwright() as p:
        browser = (p.chromium if True else p.firefox).launch(headless=(not args.headful))
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.set_default_navigation_timeout(10000)
            page.goto(args.url, wait_until="domcontentloaded")
        except Exception as e:
            print(f"ERROR: Failed to load {args.url}: {e}", file=sys.stderr)
            browser.close()
            return 2

        # Log console errors/warnings for diagnostics
        def on_console(msg):  # pragma: no cover
            try:
                print(f"[console.{msg.type}] {msg.text}")
            except Exception:
                pass
        page.on("console", on_console)

        last_dbg = ""
        while time.time() < deadline:
            ok, dbg = page_has_value_or_online(page)
            last_dbg = dbg
            if ok:
                print(f"UI check PASS: {dbg}")
                browser.close()
                return 0
            time.sleep(0.5)
            # Try a light reload mid-way
            if deadline - time.time() < args.timeout / 2:
                try:
                    page.reload(wait_until="domcontentloaded")
                except Exception:
                    pass

        print(f"UI check FAIL after {args.timeout}s: {last_dbg}", file=sys.stderr)
        try:
            # Capture a small screenshot for debugging
            page.screenshot(path="ui_check_fail.png", full_page=False)
            print("Saved screenshot: ui_check_fail.png", file=sys.stderr)
        except Exception:
            pass
        browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
