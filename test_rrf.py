import requests, json
BASE = "http://127.0.0.1:8080"
headers = {"Origin": "http://127.0.0.1:8080"}

# 历史用户 ml:14 的 RRF 融合
r = requests.get(f"{BASE}/api/v1/demo/fusion/14/recommendations", headers=headers, timeout=30)
print(f"GET fusion status={r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  sources={d['sources']}  k={d['k']}")
    print(f"  legged={len(d['leg_summaries'])} legs")
    print(f"  items={len(d['items'])}")
    for item in d["items"][:5]:
        print(f"    #{item['movie_id']} rank={item['fusion_rank']} score={item['score']:.4f} sources={item['recall_sources']} ranks={item['recall_ranks']}")
else:
    print(f"  body={r.text[:200]}")
