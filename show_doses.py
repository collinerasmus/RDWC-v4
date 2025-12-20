import requests

base = "http://192.168.88.55:8080"
resp = requests.get(f"{base}/api/ph/dose_log?hours=6&limit=20", timeout=10)
doses = resp.json()

print("=== Recent Doses (last 20) ===")
ok_count = 0
blocked_count = 0
for d in doses:
    result = d.get("result", "?")
    if result == "ok":
        ok_count += 1
    elif result == "blocked":
        blocked_count += 1

print(f"OK: {ok_count}, Blocked: {blocked_count}")
print("\nLast 5 rows:")
for d in doses[-5:]:
    ts = d.get("ts_utc", "")[-8:]
    result = d.get("result", "?")
    reason = str(d.get("reason", ""))[:40]
    pre = d.get("pre_ph")
    post = d.get("post_ph")
    vol = d.get("volume_ml")
    if pre and post:
        delta = round(post - pre, 4)
        print(f"  {ts} | {result:8} | pre={pre:.3f} post={post:.3f} Δ={delta:+.4f} vol={vol}ml | {reason}")
    else:
        print(f"  {ts} | {result:8} | no pH data | vol={vol}ml | {reason}")
