import urllib.request
# 直接请求服务器的 ExperimentsView chunk
url = "http://127.0.0.1:8080/assets/ExperimentsView-CU9EscrJ.js"
try:
    r = urllib.request.urlopen(url, timeout=10)
    body = r.read().decode()
    print(f"Status={r.status} len={len(body)}")
    print(f"Has RRF text: {'RRF 多算法融合' in body}")
    print(f"Has fusion-panel: {'fusion-panel' in body}")
except Exception as e:
    print(f"ERR: {e}")

# 看 index.html 引用了什么 chunk
url2 = "http://127.0.0.1:8080/"
r2 = urllib.request.urlopen(url2, timeout=10)
body2 = r2.read().decode()
print("\nindex.html references:")
import re
for m in re.findall(r'ExperimentsView[^"\']+', body2):
    print(f"  {m}")
