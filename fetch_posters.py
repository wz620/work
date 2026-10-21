"""批量用 OMDb API + Clash 代理下载海报图片和电影详情到本地。
用法：cd 项目根目录 && py fetch_posters.py
依赖：requests（已在 requirements.lock.txt）
"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "frontend" / "public"
POSTER_DIR = PUBLIC / "posters"
DETAILS_FILE = PUBLIC / "movie-details.json"
POSTER_DIR.mkdir(parents=True, exist_ok=True)

PROXY = "http://127.0.0.1:7897"
PROXIES = {"http": PROXY, "https": PROXY}
OMDB_KEY = "trilogy"  # 公共测试 key，够 40 部电影用

# 这 40 部是 Top-10 四个榜单的并集
MOVIES = [
    # Popular Top-10
    (318, "0111161", "Shawshank Redemption, The"),
    (356, "0109830", "Forrest Gump"),
    (296, "0110912", "Pulp Fiction"),
    (2571, "0133093", "Matrix, The"),
    (593, "0102926", "Silence of the Lambs, The"),
    (260, "0076759", "Star Wars: Episode IV - A New Hope"),
    (2959, "0137523", "Fight Club"),
    (480, "0107290", "Jurassic Park"),
    (4993, "0120737", "Lord of the Rings: The Fellowship of the Ring"),
    (527, "0108052", "Schindler's List"),
    # Cold Start Top-10
    (5, None, "Father of the Bride Part II"),
    (18, None, "Four Rooms"),
    (19, None, "Ace Ventura: When Nature Calls"),
    (65, None, "Bio-Dome"),
    (69, None, "Friday"),
    (88, None, "Black Sheep"),
    (102, None, "Mr. Wrong"),
    (104, None, "Happy Gilmore"),
    (125, None, "Flirting With Disaster"),
    (135, None, "Down Periscope"),
    # ItemCF ml:14 Top-10
    (3253, None, "Wayne's World"),
    (2502, None, "Office Space"),
    (3948, None, "Meet the Parents"),
    (1923, None, "There's Something About Mary"),
    (3033, None, "Spaceballs"),
    (5449, None, "Mr. Deeds"),
    (3552, None, "Caddyshack"),
    (3715, None, "Burglar"),
    (2797, None, "Big"),
    (1517, None, "Austin Powers: International Man of Mystery"),
    # ItemCF ml:55 Top-10
    (2000, None, "Lethal Weapon"),
    (1377, None, "Batman Returns"),
    (1101, None, "Top Gun"),
    (2268, None, "Few Good Men, A"),
    (474, None, "In the Line of Fire"),
    (2716, None, "Ghostbusters"),
    (2194, None, "Untouchables, The"),
    (377, None, "Speed"),
    (1608, None, "Air Force One"),
    (1036, None, "Die Hard"),
]

session = requests.Session()
# Amazon / OMDb 直连通，TMDB image CDN 被防火墙封；Clash 代理当前未运行
# session.proxies = PROXIES

details_map: dict[str, dict] = {}
ok, fail = 0, 0

for mid, imdb, title in MOVIES:
    j = None
    if imdb:
        url = f"https://www.omdbapi.com/?i=tt{imdb}&apikey={OMDB_KEY}&v=1"
        try:
            r = session.get(url, timeout=15)
            j = r.json() if r.status_code == 200 and r.json().get("Response") == "True" else None
        except Exception:
            j = None
    if not j:
        url = f"https://www.omdbapi.com/?t={title}&apikey={OMDB_KEY}&v=1"
        try:
            r = session.get(url, timeout=15)
            j = r.json() if r.status_code == 200 and r.json().get("Response") == "True" else None
        except Exception:
            j = None

    if not j:
        print(f"[SKIP] {mid} {title} — OMDb not found")
        details_map[str(mid)] = {}
        fail += 1
        time.sleep(0.3)
        continue

    poster_url = j.get("Poster") or ""
    poster_path = None
    if poster_url and poster_url != "N/A":
        local = POSTER_DIR / f"{mid}.jpg"
        if not local.exists():
            try:
                img = session.get(poster_url, timeout=20)
                if img.status_code == 200 and len(img.content) > 500:
                    local.write_bytes(img.content)
                    poster_path = f"/posters/{mid}.jpg"
                    ok += 1
                    print(f"[OK]   {mid} 下载海报 {len(img.content)//1024}KB")
                else:
                    print(f"[BAD]  {mid} 海报下载失败 HTTP={img.status_code}")
            except Exception as e:
                print(f"[ERR]  {mid} 海报下载异常 {e}")
        else:
            poster_path = f"/posters/{mid}.jpg"
            print(f"[HIT]  {mid} 海报已存在")

    details_map[str(mid)] = {
        "director": j.get("Director"),
        "actors": j.get("Actors"),
        "plot": j.get("Plot"),
        "rated": j.get("Rated"),
        "runtime": j.get("Runtime"),
        "imdb_rating": j.get("imdbRating"),
        "poster_local": poster_path,
        "imdb_id": j.get("imdbID"),
        "omdb_title": j.get("Title"),
        "omdb_year": j.get("Year"),
    }
    time.sleep(0.25)  # 遵守 OMDb 速率

DETAILS_FILE.write_text(json.dumps(details_map, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n完成：海报 OK={ok}  失败={fail}  详情 JSON 共 {len(details_map)} 部")
print(f"图片目录：{POSTER_DIR}")
print(f"详情文件：{DETAILS_FILE}")
