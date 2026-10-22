"""
全量补海报：给 Cinelab 数据库所有电影（8459 部）匹配 TMDB 海报 + 下载到本地。
流程：
  1. 从 /api/v1/movies 分页拉所有 movie_id + 原始 movielens_title + 年份
  2. TMDB search 匹配，拿到 tmdb_poster_path
  3. 通过代理下载 image.tmdb.org 到 frontend/public/posters/{mid}.jpg
  4. 合并到 movie-details.json（覆盖旧 70 部，新增缺失部）
代理：http://127.0.0.1:7897（Clash HTTP）
"""
import json, time, sys, re, requests
from pathlib import Path
from urllib.parse import quote

ROOT = Path("e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1")
POSTERS_DIR = ROOT / "frontend/public/posters"
DETAILS_PATH = ROOT / "frontend/public/movie-details.json"

PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/120"}
TMDB_KEY = "61572be02f0a068658828f6396aacf60"
BASE = "http://127.0.0.1:8080"

POSTERS_DIR.mkdir(parents=True, exist_ok=True)


# ========= 1. 拉所有电影 =========
def fetch_all_movies():
    page, per_page = 1, 100
    all_movies = []
    total = None
    while True:
        r = requests.get(f"{BASE}/api/v1/movies", params={"page": page, "per_page": per_page}, timeout=15)
        if r.status_code != 200:
            print(f"[WARN] /movies page {page} → {r.status_code}")
            break
        data = r.json()
        if total is None:
            total = data["total"]
            print(f"数据库共 {total} 部电影")
        batch = data["items"]
        all_movies.extend(batch)
        print(f"  page {page}: {len(batch)} 部, 累计 {len(all_movies)}/{total}")
        if len(all_movies) >= total or not batch:
            break
        page += 1
        time.sleep(0.2)
    return all_movies


def clean_title(raw: str) -> tuple[str, int | None]:
    """去掉括号年份等杂质，返回 (clean_title, year)"""
    raw = raw.strip()
    year = None
    m = re.search(r'\((19\d{2}|20\d{2})\)', raw)
    if m:
        year = int(m.group(1))
        raw = raw[:m.start()].strip()
    # 去掉尾部的 1990s / 2000s
    raw = re.sub(r'\s*\(\d{4}s\)\s*$', '', raw).strip()
    return raw, year


# ========= 2. TMDB 匹配 =========
def tmdb_search(title: str, year: int | None = None) -> dict | None:
    params = {"api_key": TMDB_KEY, "query": title, "language": "en-US"}
    if year:
        params["year"] = year
    try:
        r = requests.get("https://api.themoviedb.org/3/search/movie", params=params, proxies=PROXIES, timeout=15)
        if r.status_code == 429:
            time.sleep(2)
            return None
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        if not results:
            return None
        best = results[0]
        # 年份差异 <= 2 年才认为匹配成功（如果指定了 year）
        if year:
            ryear = best.get("release_date", "")[:4]
            if ryear and abs(int(ryear) - year) > 2:
                return None
        return best
    except Exception:
        return None


# ========= 3. 下载海报 =========
def download_poster(mid: str, poster_path: str) -> bool:
    dst = POSTERS_DIR / f"{mid}.jpg"
    if dst.exists() and dst.stat().st_size > 5000:
        return True
    try:
        url = f"https://image.tmdb.org/t/p/w342{poster_path}"
        r = requests.get(url, headers=HEADERS, proxies=PROXIES, timeout=25)
        if r.status_code == 200 and len(r.content) > 5000:
            dst.write_bytes(r.content)
            return True
        return False
    except Exception:
        return False


# ========= 主流程 =========
def main():
    # 加载已有 movie-details.json（包含 director/actors 等）
    old = {}
    if DETAILS_PATH.exists():
        old = json.loads(DETAILS_PATH.read_text(encoding="utf-8"))
        print(f"已有 {len(old)} 条 movie-details.json")

    all_movies = fetch_all_movies()
    print(f"\n=== 开始匹配 {len(all_movies)} 部电影 ===\n")

    success_match = 0  # TMDB 匹配到 poster_path
    success_down = 0   # 海报下载成功
    no_match = 0       # TMDB 搜不到
    fail_down = 0      # 有 poster_path 但下载失败
    skipped = 0        # 已有 poster_local 且文件存在

    # 每个电影的结果存到这里，最后统一写 JSON
    new_details = dict(old)  # 保留旧 70 部的 imdb_rating/director 等
    tmdb_cache = {}  # title+year → tmdb result，避免重复搜索

    for i, m in enumerate(all_movies):
        mid = str(m["movie_id"])
        title_raw = m.get("movielens_title", "")
        title_zh = m.get("title_zh", "")
        title, year = clean_title(title_raw)

        # 已有并且文件存在 → 跳过
        existing = old.get(mid, {})
        existing_local = existing.get("poster_local")
        if existing_local and (POSTERS_DIR / f"{mid}.jpg").exists():
            skipped += 1
            if i % 100 == 0:
                print(f"  [{i+1}/{len(all_movies)}] 跳过 #{mid} {title_zh or title[:30]} (已有)")
            continue

        # TMDB search（带缓存）
        cache_key = f"{title.lower()}|{year or ''}"
        if cache_key in tmdb_cache:
            result = tmdb_cache[cache_key]
        else:
            result = tmdb_search(title, year)
            if not result and year:
                # 再试不带年份
                result = tmdb_search(title, None)
            tmdb_cache[cache_key] = result
            time.sleep(0.1)

        if not result or not result.get("poster_path"):
            no_match += 1
            if i % 50 == 0:
                print(f"  [{i+1}/{len(all_movies)}] ✗ #{mid} {title[:30]} — 没匹配到")
            continue

        success_match += 1
        poster_path = result["poster_path"]

        if download_poster(mid, poster_path):
            success_down += 1
            # 合并到 JSON
            entry = dict(existing)
            entry["poster_local"] = f"/posters/{mid}.jpg"
            entry["tmdb_poster_path"] = poster_path
            if result.get("id"):
                entry["tmdb_id"] = result["id"]
            # 保留旧的 director/actors/imdb_rating 等（如果已有）
            new_details[mid] = entry
            if (i + 1) % 50 == 0:
                n = len(list(POSTERS_DIR.glob("*.jpg")))
                print(f"  [{i+1}/{len(all_movies)}] ✓ #{mid} {title[:30]} +{n}张")
        else:
            fail_down += 1
            print(f"  [{i+1}/{len(all_movies)}] ✗ #{mid} {title[:30]} — 下载失败 {poster_path}")

        # 每 500 部保存一次进度，防止中途挂掉
        if (i + 1) % 500 == 0:
            DETAILS_PATH.write_text(json.dumps(new_details, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  [checkpoint] 已保存 {len(new_details)} 条到 movie-details.json")

    # 最终保存
    DETAILS_PATH.write_text(json.dumps(new_details, indent=2, ensure_ascii=False), encoding="utf-8")

    jpg_count = len(list(POSTERS_DIR.glob("*.jpg")))
    with_local = sum(1 for v in new_details.values() if v.get("poster_local"))

    print(f"\n=== 最终统计 ===")
    print(f"处理: {len(all_movies)} 部")
    print(f"  跳过（已有）: {skipped}")
    print(f"  TMDB 匹配成功: {success_match}")
    print(f"  下载成功: {success_down}")
    print(f"  TMDB 没匹配: {no_match}")
    print(f"  下载失败: {fail_down}")
    print(f"\nposters/ 目录: {jpg_count} 张")
    print(f"movie-details.json 有 poster_local: {with_local}")
    print(f"未覆盖（需要优雅 fallback）: {len(all_movies) - with_local}")


if __name__ == "__main__":
    main()
