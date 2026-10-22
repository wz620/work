import requests
BASE = "http://127.0.0.1:8080"
s = requests.Session()

# Step 1: get CSRF cookie
r = s.get(f"{BASE}/api/v1/auth/csrf", headers={"Origin": BASE})
print(f"1. GET /auth/csrf → {r.status_code}")
print(f"   cookies: {dict(s.cookies)}")
csrf_cookie = s.cookies.get("course_csrf", "")
print(f"   course_csrf cookie value: {csrf_cookie[:60]}…")

# Step 2: login
h = {"Origin": BASE, "Content-Type": "application/json", "X-CSRF-Token": csrf_cookie}
r = s.post(f"{BASE}/api/v1/auth/login",
           json={"login": "testuser", "password": "thisisalongpw123"}, headers=h)
print(f"2. POST /auth/login → {r.status_code}")
print(f"   response: {r.text[:150]}")
print(f"   cookies now: {dict(s.cookies)}")
csrf_after = s.cookies.get("course_csrf", "")
print(f"   course_csrf now: {csrf_after[:60]}…")

# Step 3: try chat with fresh CSRF
r = s.get(f"{BASE}/api/v1/auth/csrf", headers={"Origin": BASE})
csrf_final = s.cookies.get("course_csrf", "")
print(f"\n3. Fresh CSRF → cookie={csrf_final[:60]}…")

h2 = {"Origin": BASE, "Content-Type": "application/json", "X-CSRF-Token": csrf_final}
r = s.post(f"{BASE}/api/v1/assistant/chat",
           json={"message": "推荐 5 部喜剧"}, headers=h2)
print(f"4. POST /assistant/chat → {r.status_code}")
print(f"   body: {r.text[:200]}")
print(f"   response headers: {dict(r.headers)}")

# Step 4: raw curl comparison
print("\n--- 用 curl 直接测 ---")
import subprocess
out = subprocess.run(["curl.exe", "-s", "-v", "-X", "POST",
                      f"{BASE}/api/v1/assistant/chat",
                      "-H", "Content-Type: application/json",
                      "-H", f"Origin: {BASE}",
                      "-d", '{"message":"推荐电影"}'],
                     capture_output=True, text=True, timeout=10)
print(out.stderr[-500:] if out.stderr else "(no stderr)")
print("stdout:", out.stdout[:200])
