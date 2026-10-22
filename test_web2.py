import urllib.request, re
# 看首页 index.html
r = urllib.request.urlopen("http://127.0.0.1:8080/", timeout=10)
body = r.read().decode()
print("Status:", r.status)
print("scripts:")
for m in re.findall(r'<script[^>]*src="([^"]+)"', body):
    print(f"  {m}")
print("links:")
for m in re.findall(r'<link[^>]*href="([^"]+)"', body):
    print(f"  {m}")
# 找所有 asset 引用
print("\nall assets:")
for m in re.findall(r'/(?:assets|public)/[^"\' ]+', body):
    print(f"  {m}")
