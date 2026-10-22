import json, csv

d = json.load(open("frontend/public/movie-details.json"))

# 缺本地海报但有 tmdb_poster_path 的
need = [(k, v) for k, v in d.items() if not v.get("poster_local") and v.get("tmdb_poster_path")]

print(f"需下载: {len(need)} 张\n")

# 输出 CSV 方便浏览器 Agent 用
with open("posters_to_download.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["movie_id", "tmdb_path", "full_url"])
    for key, v in need:
        url = f"https://image.tmdb.org{t['tmdb_poster_path']}"
        print(f"  #{key} {v.get('omdb_title','?')[:30]} → {url}")
        w.writerow([key, v["tmdb_poster_path"], url])

print(f"\n已写入 posters_to_download.csv")
print(f"全量下载脚本: python download_tmdb_posters_browser.py")
