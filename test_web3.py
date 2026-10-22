import urllib.request, re
# 查主 bundle 里动态 import 的 ExperimentsView chunk 名
r = urllib.request.urlopen("http://127.0.0.1:8080/assets/index-y_2wqajP.js", timeout=15)
body = r.read().decode()
# 找 ExperimentsView 动态 import
matches = re.findall(r'ExperimentsView[^"\']*', body)
print("ExperimentsView refs in index-y_2wqajP.js:", matches[:5])

# 查它引用的 hash 字符串
m = re.search(r'E\(\(\)\s*=>\s*import\("\./ExperimentsView-([^"]+)"\)', body)
if m:
    print(f"\nDynamic import chunk name: ExperimentsView-{m.group(1)}")
    chunk_name = f"ExperimentsView-{m.group(1)}"
    chunk_url = f"http://127.0.0.1:8080/assets/{chunk_name}"
    r2 = urllib.request.urlopen(chunk_url, timeout=10)
    chunk_body = r2.read().decode()
    print(f"Chunk HTTP {r2.status}, len={len(chunk_body)}, has RRF: {'RRF 多算法融合' in chunk_body}")
else:
    # 另一种模式
    for m2 in re.finditer(r'ExperimentsView-([A-Za-z0-9]+)', body):
        print(f"  found: ExperimentsView-{m2.group(1)}")
