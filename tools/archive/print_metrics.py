from playwright.sync_api import sync_playwright
import sys
url=sys.argv[1] if len(sys.argv)>1 else 'http://localhost:8080/'
with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    pg=b.new_page()
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    def txt(sel):
        try:
            return (pg.query_selector(sel).text_content() or '').strip()
        except Exception:
            return ''
    vals={
        'val-temp':txt('#val-temp'),
        'val-ec':txt('#val-ec'),
        'val-ph':txt('#val-ph'),
        'badge':txt('#sensors-online'),
    }
    print(vals)
    b.close()
