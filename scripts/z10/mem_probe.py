# Z10 재현: python scripts/z10/gen_fixtures.py <dir> 후 python scripts/z10/mem_probe.py <dir> bh|pl (PROBE_WARM=1 PROBE_CONC=1|2) — 레포 루트에서.
"""네이버 상세 본문 사진 올리기(cdn_map — 사전검증의 detail_judge 단계) 1회의 RSS — 새 프로세스. argv: fxdir set(bh|pl).
네트워크는 가짜: 사진 받기 = 디스크 바이트, 업로드 = 진짜 multipart → 진짜 릴레이 봉투(base64·JSON)까지 만들고 가짜 응답."""
import os, sys, json, base64, time, gc
sys.path.insert(0, os.getcwd())
fx, which = sys.argv[1], sys.argv[2]
os.environ.update(MARKET_API_RELAY_URL="https://relay.test/mkt.php", MARKET_API_RELAY_KEY="k", FX_USE_LIVE="0")
def rss():
    d = {}
    for line in open("/proc/self/status"):
        if line.startswith(("VmRSS:", "VmHWM:")):
            k, v = line.split(":"); d[k] = int(v.split()[0]) // 1024
    return d["VmRSS"], d["VmHWM"]
files = sorted(f for f in os.listdir(fx) if f.startswith(which + "_"))
BLOBS = {f"https://img.alicdn.com/imgextra/{f}": open(os.path.join(fx, f), "rb").read() for f in files}
import requests
class R:
    def __init__(self, body, ct): self.content, self.status_code, self.headers = body, 200, {"Content-Type": ct}
    def raise_for_status(self): pass
def fake_get(url, *a, **k):
    b = BLOBS[url.split("?")[0]]
    return R(b, "image/png" if url.endswith(".png") else ("image/webp" if url.endswith(".webp") else "image/jpeg"))
requests.get = fake_get
import src.market_relay as MR
class RR:
    status_code = 200
    def __init__(self, n): self._n = n
    def json(self):
        body = json.dumps({"images": [{"url": f"https://shop-phinf.pstatic.net/x{i}.jpg"} for i in range(self._n)]})
        return {"status": 200, "body_b64": base64.b64encode(body.encode()).decode(), "content_type": "application/json"}
SENT = []
def fake_post(url, json=None, **k):
    raw = base64.b64decode(json["body_b64"])
    n = raw.count(b'name="imageFiles"')
    SENT.append((n, len(raw)))
    return RR(n)
MR.requests.post = fake_post
from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
SS._get_access_token = lambda self: "tok"
import src.uploaders.naver_cdn_cache as CC
CC.get = lambda *a, **k: None; CC.put = lambda *a, **k: None; CC.put_fail = lambda *a, **k: None
up = SS(account=None)
if os.environ.get("PROBE_WARM"):
    # 예열: 같은 경로를 작은 사진 1장으로 한 번 — 첫 호출의 지연 import(PIL 플러그인 등)를 기준선에 넣는다(운영 워커는 이미 데워져 있다)
    from PIL import Image as _I
    import io as _io
    _b = _io.BytesIO(); _I.new("RGB", (64, 64), (200, 10, 10)).save(_b, "PNG")
    BLOBS["https://img.alicdn.com/imgextra/warm.png"] = _b.getvalue() * 1 + b""
    up.cdn_map(["https://img.alicdn.com/imgextra/warm.png"]); del BLOBS["https://img.alicdn.com/imgextra/warm.png"]; SENT.clear()
gc.collect()
r0, h0 = rss()
t0 = time.monotonic()
import threading
CONC = int(os.environ.get("PROBE_CONC", "1"))
try:
    import src.seller_console.views as V
    sem = V._pv_semaphore()                      # Z10: 사전검증 잡은 프로세스당 1개(새 코드)
except Exception:
    sem = None                                    # 옛 코드: 줄 서기 없음
outs = []
def run():
    if sem is not None:
        with sem:
            outs.append(up.cdn_map(list(BLOBS)))
    else:
        outs.append(up.cdn_map(list(BLOBS)))
ths = [threading.Thread(target=run) for _ in range(CONC)]
[t.start() for t in ths]; [t.join() for t in ths]
out = outs[0]
ms = int((time.monotonic() - t0) * 1000)
r1, h1 = rss()
gc.collect()
r2, _ = rss()
print(json.dumps({"set": which, "images": len(BLOBS), "bytes_in": sum(len(b) for b in BLOBS.values()),
                  "rss_before": r0, "peak_delta_mb": h1 - r0, "after_mb_delta": r2 - r0, "ms": ms,
                  "uploads": [{"imgs": n, "bytes": b} for n, b in SENT], "kept": len(out["mapping"]), "dropped": len(out["dropped"])}))
