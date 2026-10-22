"""测试 explain endpoint —— 用 history user，直接 POST，不用登录。"""
import json, requests

BASE = "http://127.0.0.1:8080"
HEADERS = {"Origin": "http://127.0.0.1:8080", "Content-Type": "application/json"}

# 先确认 history user 存在
r = requests.get(f"{BASE}/api/v1/experiments/algorithms")
print(f"algorithms: {r.json()}")

# Content：历史用户 ml:14
print("\n=== Content ml:14 电影#1 (Toy Story) ===")
r = requests.post(f"{BASE}/api/v1/assistant/explain-recommendation",
           json={"algorithm": "content", "movie_id": "1", "source": "ml", "subject_id": "14", "limit": 10},
           headers=HEADERS)
print(f"status={r.status_code}")
d = r.json()
print(json.dumps(d, ensure_ascii=False, indent=2)[:800])

# ItemCF：历史用户 ml:14
print("\n=== ItemCF ml:14 电影#1 ===")
r = requests.post(f"{BASE}/api/v1/assistant/explain-recommendation",
           json={"algorithm": "itemcf", "movie_id": "1", "source": "ml", "subject_id": "14", "limit": 10},
           headers=HEADERS)
print(f"status={r.status_code}")
d = r.json()
print(json.dumps(d, ensure_ascii=False, indent=2)[:800])
