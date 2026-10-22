"""快速测试：用已有 39 张海报里的一张，看 Amazon CDN 现在还能不能通。然后测试各种 CDN 变体。"""
import requests, ssl, sys, time

HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/120"}

tests = [
    # 已成功的 Amazon CDN URL（来自之前 fetch_posters.py 的 OMDb 返回）
    ("Amazon CDN 已有海报", "https://m.media-amazon.com/images/M/MV5BMDA1ODU5YjAtMTZlMS00YjY4LTg4NWMtNzU5YzUwOWEyMWJjL2ltYWdlL2ltYWdlXkEyXkFqcGdeQXVyMTQxNzMzNDI@._V1_.jpg"),
    # TMDB CDN
    ("TMDB", "https://image.tmdb.org/t/p/w342/jWBDz6Mf9aQVBiUS76JQsEhvoJl.jpg"),
    # IMDB CDN
    ("IMDB ia", "https://ia.media-imdb.com/images/M/MV5BMDA1ODU5YjAtMTZlMS00YjY4LTg4NWMtNzU5YzUwOWEyMWJjL2ltYWdlL2ltYWdlXkEyXkFqcGdeQXVyMTQxNzMzNDI@._V1_.jpg"),
    # 各种代理/镜像
    ("fastly img.tmdb", "https://img.tmdb.org/t/p/w342/jWBDz6Mf9aQVBiUS76JQsEhvoJl.jpg"),
    ("images2.tmdb", "https://images2.tmdb.org/t/p/w342/jWBDz6Mf9aQVBiUS76JQsEhvoJl.jpg"),
    ("images3.tmdb", "https://images3.tmdb.org/t/p/w342/jWBDz6Mf9aQVBiUS76JQsEhvoJl.jpg"),
    ("images4.tmdb", "https://images4.tmdb.org/t/p/w342/jWBDz6Mf9aQVBiUS76JQsEhvoJl.jpg"),
    ("images5.tmdb", "https://images5.tmdb.org/t/p/w342/jWBDz6Mf9aQVBiUS76JQsEhvoJl.jpg"),
    ("tmdbcdn", "https://cdn.tmdb.org/t/p/w342/jWBDz6Mf9aQVBiUS76JQsEhvoJl.jpg"),
    # HTTP 非 HTTPS
    ("HTTP TMDB", "http://image.tmdb.org/t/p/w342/jWBDz6Mf9aQVBiUS76JQsEhvoJl.jpg"),
    ("HTTP Amazon", "http://m.media-amazon.com/images/M/MV5BMDA1ODU5YjAtMTZlMS00YjY4LTg4NWMtNzU5YzUwOWEyMWJjL2ltYWdlL2ltYWdlXkEyXkFqcGdeQXVyMTQxNzMzNDI@._V1_.jpg"),
]

for name, url in tests:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False, allow_redirects=True)
        size = len(r.content)
        ok = r.ok and size > 5000
        tag = "✓" if ok else "✗"
        print(f"{tag} {name:20} → status={r.status_code:3} size={size:>7}B  {url[:60]}")
    except Exception as e:
        print(f"✗ {name:20} → {type(e).__name__}: {str(e)[:50]}")
    time.sleep(0.3)
