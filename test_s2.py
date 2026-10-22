import requests
BASE = "http://127.0.0.1:8080"

# 先拿 CSRF + 登录
s = requests.Session()
s.get(f"{BASE}/api/v1/auth/csrf", timeout=5)
csrf = s.cookies.get("csrf_token", "")
origin = {"Origin": BASE, "X-CSRF-Token": csrf, "Content-Type": "application/json"}
s.post(f"{BASE}/api/v1/auth/login", json={"login": "testuser", "password": "thisisalongpw123"},
       headers=origin, timeout=5)

# 测 S2 assistant/chat
payload = {"message": "给我推荐 5 部喜剧电影，用 Content 算法"}
r = s.post(f"{BASE}/api/v1/assistant/chat", json=payload, headers=origin, timeout=30)
print(f"S2 /assistant/chat status={r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  mode={d['mode']}")
    print(f"  tool_calls: {[(t['name'], t['status']) for t in d['tool_calls']]}")
    print(f"  answer: {d['answer'][:400]}")
else:
    print(f"  body={r.text[:300]}")

# 再试一个
payload2 = {"message": "我昨天看了电影 Toy Story，帮我找类似的"}
csrf2 = s.cookies.get("csrf_token", "")
origin2 = {"Origin": BASE, "X-CSRF-Token": csrf2, "Content-Type": "application/json"}
r2 = s.post(f"{BASE}/api/v1/assistant/chat", json=payload2, headers=origin2, timeout=30)
print(f"\nS2 #2 status={r2.status_code}")
if r2.status_code == 200:
    d2 = r2.json()
    print(f"  mode={d2['mode']}")
    print(f"  tool_calls: {[(t['name'], t['status']) for t in d2['tool_calls']]}")
    print(f"  answer: {d2['answer'][:400]}")
else:
    print(f"  body={r2.text[:300]}")
