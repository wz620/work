import urllib.request
# 模拟浏览器的 Accept-Encoding: gzip
url = "http://127.0.0.1:8080/assets/ExperimentsView-CU9EscrJ.js"
req = urllib.request.Request(url)
req.add_header("Accept-Encoding", "gzip, deflate")
req.add_header("Cache-Control", "no-cache")
req.add_header("Pragma", "no-cache")
try:
    import gzip
    r = urllib.request.urlopen(req, timeout=10)
    body = r.read()
    print(f"Status={r.status}")
    print(f"Content-Encoding: {r.headers.get('Content-Encoding')}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    print(f"Last-Modified: {r.headers.get('Last-Modified')}")
    print(f"Cache-Control: {r.headers.get('Cache-Control')}")
    print(f"ETag: {r.headers.get('ETag')}")
    print(f"Body len raw={len(body)}")
    if r.headers.get('Content-Encoding') == 'gzip':
        body = gzip.decompress(body)
    text = body.decode()
    print(f"Text len={len(text)}")
    print(f"Has RRF text: {'RRF 多算法融合' in text}")
except Exception as e:
    import traceback; traceback.print_exc()
