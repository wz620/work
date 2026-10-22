import json, requests
BASE = "http://127.0.0.1:8080"
headers = {"Origin": "http://127.0.0.1:8080", "Content-Type": "application/json"}

# Content ml:14 movie#1
payload = {"algorithm": "content", "movie_id": "1", "source": "ml", "subject_id": "14", "limit": 10}
r = requests.post(f"{BASE}/api/v1/assistant/explain-recommendation", json=payload, headers=headers)
print(f"Content status={r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  found={d['evidence'].get('found')} mode={d.get('explanation_mode')}")
    print(f"  explanation: {d.get('explanation','')[:150]}")
else:
    print(f"  body={r.text[:200]}")

# ItemCF
payload = {"algorithm": "itemcf", "movie_id": "1", "source": "ml", "subject_id": "14", "limit": 10}
r = requests.post(f"{BASE}/api/v1/assistant/explain-recommendation", json=payload, headers=headers)
print(f"\nItemCF status={r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  found={d['evidence'].get('found')} mode={d.get('explanation_mode')}")
    print(f"  explanation: {d.get('explanation','')[:150]}")
else:
    print(f"  body={r.text[:200]}")
