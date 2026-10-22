"""四个扩展功能完整展示 — 最终版"""
import json, requests

BASE = "http://127.0.0.1:8080"
s = requests.Session()
H = {"Origin": BASE, "Accept": "application/json"}

def csrf_headers():
    """每次 POST 前先 GET /auth/csrf 拿 nonce"""
    r = s.get(f"{BASE}/api/v1/auth/csrf", headers=H, timeout=5)
    return {**H, "Content-Type": "application/json", "X-CSRF-Token": r.json()["csrf_token"]}

# ===== 登录 =====
print("🔐 登录 testuser …")
r = s.post(f"{BASE}/api/v1/auth/login",
           json={"login_name": "testuser", "password": "thisisalongpw123"},
           headers=csrf_headers(), timeout=5)
if r.status_code != 200:
    print(f"  ❌ 登录失败 {r.status_code} {r.text}")
else:
    print(f"  ✓ 登录成功 account={r.json()['account']['account_id']}")

def sect(title):
    print("\n" + "=" * 60 + f"\n  {title}\n" + "=" * 60)

# ===== S1 =====
sect("S1：RRF 多算法融合 — 5 路召回 × Reciprocal Rank Fusion")
r = s.get(f"{BASE}/api/v1/demo/fusion/14/recommendations", headers=H, timeout=30)
d = r.json()
print(f"✓ HTTP 200  sources={d['sources']}  k={d['k']}")
print(f"  公式：score(m) = Σ 1/(k+rank_s(m))")
print(f"  每路召回 Top-50 → 去重合并 → 排序取 Top-10")
print()
print(f"  {'rank':<6}{'movie_id':<10}{'RRF_score':<10}{'召回来源':<28}原始排名")
for it in d["items"][:10]:
    src = ",".join(it["recall_sources"])
    rks = ", ".join(f"{k}=#{v}" for k, v in it["recall_ranks"].items())
    print(f"  #{it['fusion_rank']:<5}{it['movie_id']:<10}{it['score']:.4f}    {src:<26}{rks}")

# ===== S2 =====
sect("S2：LLM 自然语言推荐交互 — 工具调用 Agent")
print("  离线 local_rules 兜底：关键词匹配 → 4 个只读工具 → 真实数据 → 总结回答")
print("  在线 LLM 模式：OpenAI 兼容 function calling → 同样 4 工具 → 自然语言回答")
for q in ["推荐 5 部动画电影", "我最近喜欢什么类型？", "查一下电影 #1 Toy Story"]:
    r = s.post(f"{BASE}/api/v1/assistant/chat",
               json={"message": q}, headers=csrf_headers(), timeout=30)
    print(f"\n  ── Q：「{q}」")
    if r.status_code != 200:
        print(f"  ❌ HTTP {r.status_code}  {r.text[:120]}"); continue
    d = r.json()
    print(f"  ✓ HTTP 200  mode={d['mode']}")
    for tc in d["tool_calls"]:
        print(f"    ⚙  [{tc['status']}] {tc['name']}  args={json.dumps(tc['arguments'],ensure_ascii=False)[:80]}")
    print(f"  💬 回答：{d['answer']}")

# ===== S3 =====
sect("S3：Kafka/InProcBus 实时行为推荐")
print("  kafka_bootstrap=None → 自动降级 InProcBus（进程内 EventBus）")
print("  每发一个 rating/favorite 事件 → consume() 更新用户画像 → 实时出 Top-10")
for i, (etype, mid, rating) in enumerate([
    ("rating","318",5.0), ("rating","2571",4.5), ("rating","50",4.0), ("favorite","296",None)], 1):
    body = {"event_type": etype, "movie_id": mid}
    if rating is not None: body["rating"] = rating
    r = s.post(f"{BASE}/api/v1/demo/realtime/events",
               json=body, headers=csrf_headers(), timeout=15)
    if r.status_code != 200:
        print(f"  #{i} {etype} mid={mid} → ❌ {r.status_code} {r.text[:100]}"); continue
    pkg = r.json(); rec = pkg["recommendation"]
    tag = "⚡InProcBus" if rec["degraded"] else "📨Kafka"
    print(f"  #{i}  {etype} movie={mid} rating={rating}  →  {tag}  algo={rec['algorithm']}")
    for it in rec["items"][:3]:
        print(f"     #{it['rank']}  movie_id={it['movie_id']}  score={it['score']:.4f}")

# ===== S4 =====
sect("S4：大模型个性化推荐解释 — Content vs ItemCF 对比")
print("  算法依据直接从算法真实计算过程提取（不是编造）")
print("  Content → genres 画像权重  ItemCF → 协同相似度 × 评分贡献")
print("  LLM 可用走 ChatClient 生成自然语言解释；不可用走 local_rules 模板")
for algo in ["content", "itemcf"]:
    r = s.post(f"{BASE}/api/v1/assistant/explain-recommendation",
               json={"algorithm": algo, "movie_id": "1", "source": "ml",
                     "subject_id": "14", "limit": 10},
               headers=csrf_headers(), timeout=30)
    print(f"\n  ── 【{algo.upper()}】  movie_id=#1 Toy Story  subject=ml:14")
    if r.status_code != 200:
        print(f"  ❌ HTTP {r.status_code}  {r.text[:120]}"); continue
    d = r.json(); ev = d["evidence"]
    print(f"  ✓ HTTP 200  mode={d['explanation_mode']}  final_score={ev['score']:.4f}")
    if algo == "content":
        print(f"  候选电影 genres 分布：{ev['target_genres']}")
        print(f"  contributing_genres（🟢 画像偏好  🔴 画像厌恶）：")
        for g in ev["contributing_genres"]:
            flag = "🟢" if g["profile_weight"] > 0 else "🔴"
            print(f"      {flag} {g['genre']:<14} profile_weight={g['profile_weight']:+.2f}")
        print(f"  种子样本（用户评分>3.0 的历史）：")
        for sm in ev["user_history_genres_sample"][:3]:
            print(f"      #{sm['movie_id']}  rating={sm['rating']}  genres={sm['genres']}")
    else:
        print(f"  top_contributions（按 |sim×rating| 排序，决定最终分数）：")
        for c in ev["top_contributions"][:5]:
            bar = "█" * int(max(0, c["similarity"]) * 25)
            print(f"      seed #{c['seed_movie_id']}  rating={c['rating']}  sim={c['similarity']:.4f}{bar}  contribution={c['contribution']:.4f}")
    print(f"  💬 AI 解释：{d['explanation']}")
