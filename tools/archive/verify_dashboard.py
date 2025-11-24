#!/usr/bin/env python3
"""
Quick dashboard verification - checks that sensors card shows values (or stale fallback)
and relay buttons are rendered.
"""
import sys
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

URL = "http://192.168.88.49:8080"
TIMEOUT_MS = 10000

def main():
    print(f"[Verify] Opening {URL} ...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Show browser for visual check
        page = browser.new_page()
        
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            print("[Verify] Page loaded")
            
            # Wait a bit for pollers to run
            time.sleep(4)
            
            # Check Sensors card
            print("\n=== SENSORS CARD ===")
            try:
                temp_el = page.locator("#val-temp").first
                ec_el = page.locator("#val-ec").first
                ph_el = page.locator("#val-ph").first
                badge_el = page.locator("#sensors-online").first
                
                temp_val = temp_el.inner_text(timeout=2000)
                ec_val = ec_el.inner_text(timeout=2000)
                ph_val = ph_el.inner_text(timeout=2000)
                badge_val = badge_el.inner_text(timeout=2000)
                
                print(f"  Temperature: {temp_val}")
                print(f"  EC: {ec_val}")
                print(f"  pH: {ph_val}")
                print(f"  Badge: {badge_val}")
                
                # Check if we have at least one value (not "--")
                has_values = any(v not in ("--", "", None) for v in (temp_val, ec_val, ph_val))
                
                if has_values:
                    print("  ✅ Sensors card showing values!")
                else:
                    print("  ⚠️  Sensors card showing '--' (checking for stale fallback...)")
                    
                    # Check if "stale" or "ago" appears in updated timestamp
                    updated_el = page.locator("#sensors-updated").first
                    updated_text = updated_el.inner_text(timeout=2000)
                    print(f"  Last update: {updated_text}")
                    
                    if "stale" in updated_text.lower() or "ago" in updated_text.lower():
                        print("  ✅ Showing stale fallback from DB")
                    else:
                        print("  ❌ No values and no stale indicator")
                        
            except Exception as e:
                print(f"  ❌ Error checking sensors: {e}")
            
            # Check Relays card
            print("\n=== RELAYS CARD ===")
            try:
                # Look for relay buttons
                relay_buttons = page.locator(".relay").all()
                print(f"  Found {len(relay_buttons)} relay buttons")
                
                if len(relay_buttons) > 0:
                    print("  ✅ Relay buttons rendered!")
                    # Show first few
                    for i, btn in enumerate(relay_buttons[:3]):
                        text = btn.inner_text(timeout=1000)
                        print(f"    Button {i+1}: {text}")
                else:
                    print("  ❌ No relay buttons found")
                    
            except Exception as e:
                print(f"  ❌ Error checking relays: {e}")
            
            # Check for console errors
            print("\n=== CONSOLE ERRORS ===")
            page.on("console", lambda msg: print(f"  Console: {msg.text}") if msg.type == "error" else None)
            time.sleep(2)
            
            print("\n=== VISUAL CHECK ===")
            print("Browser window is open. Please visually confirm:")
            print("  1. Sensors card shows numbers OR 'stale (Xs ago)' label")
            print("  2. Online/Offline badge is visible")
            print("  3. Relay buttons are visible and show ON/OFF state")
            print("  4. No red JavaScript errors in browser console (F12)")
            print("\nPress Enter when done checking, or Ctrl+C to abort...")
            input()
            
            print("\n✅ Visual verification complete")
            
        except PlaywrightTimeout as e:
            print(f"❌ Timeout: {e}")
            return 1
        except KeyboardInterrupt:
            print("\n⚠️  Verification cancelled by user")
            return 1
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            browser.close()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
