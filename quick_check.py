from app.settings import get_all_settings
s = get_all_settings()
print(f"pH: {s.get('targets.ph_low')}-{s.get('targets.ph_high')}")
print(f"EC: {s.get('targets.ec_low')}-{s.get('targets.ec_high')}")
