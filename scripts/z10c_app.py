"""Z10-C 측정용 WSGI 앱 — 운영 앱(`src.order_webhook:app`)을 그대로 띄우되 바깥 호출만 막는다.

`scripts/z10c_measure.py`가 이 모듈을 gunicorn으로 띄운다(전 = main 워크트리, 후 = 브랜치 — cwd의 코드를 쓴다).
- alicdn 사진 → `Z10C_FIX` 폴더의 실제 BLACKHOLES 5장(가짜 이미지 아님), 텐센트 OCR·Cloudinary·네이버 업로드는 응답만 흉내.
- 수집 상품 1건을 미리 넣어 둔다(preload — master에서 넣고 워커가 물려받는다). 셀러 = 로그인 없는 기본 셀러.
- `POST /__z10c/pv` = 사전검증의 무거운 구간(쿠팡 대표 사진 판정 + 네이버 상세 사전 올리기)을 **동시에** — Z10-B 하네스와 같은 일.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
os.environ.setdefault("FX_USE_LIVE", "0")
os.environ.setdefault("FX_DISABLE_NETWORK", "1")
for _k, _v in dict(COUPANG_ACCESS_KEY="harness", COUPANG_SECRET_KEY="harness", COUPANG_VENDOR_ID="A00000000",
                   NAVER_CLIENT_ID="harness", NAVER_CLIENT_SECRET="$2a$10$abcdefghijklmnopqrstuv").items():
    os.environ.setdefault(_k, _v)                          # 가짜 키 — 아래에서 마켓 API 호출은 503으로 막는다
os.environ.update(CLOUDINARY_CLOUD_NAME="x", CLOUDINARY_API_KEY="x", CLOUDINARY_API_SECRET="x", COUPANG_IMAGE_CHECK="1")
sys.path.insert(0, os.getcwd())

FIX = Path(os.environ["Z10C_FIX"]).resolve()
CDN_DIR = Path(os.environ.get("Z10C_CDN_DIR", "/tmp"))
URLS = [
    "https://img.alicdn.com/imgextra/i2/3596090318/O1CN01yqZT4K3oxSKAOX2W_!!3596090318.png",
    "https://img.alicdn.com/imgextra/i3/3596090318/O1CN01yaWvo3SdZoFCfVya~crop,1076,0,4160,4160~_!!3596090318.jpg",
    "https://img.alicdn.com/imgextra/i1/3596090318/O1CN01f9Vrp5CshwF8RgLQ_!!3596090318.jpg",
    "https://img.alicdn.com/imgextra/i3/3596090318/O1CN01mSzsbHs19FB8RgLQ_!!3596090318.jpg",
    "https://img.alicdn.com/imgextra/i2/3596090318/O1CN01sf6y0qmpYhB8RgLQ_!!3596090318.jpg",
]


def _file_for(url: str) -> Path:
    tail = url.rsplit("/", 1)[-1]
    p = FIX / tail
    if p.exists():
        return p
    stem = tail.split("~")[0].split("_!!")[0]
    hits = sorted(FIX.glob(stem + "*"))
    return hits[0]


def _bytes(url: str) -> bytes:
    return _file_for(url).read_bytes()


class _Resp:
    def __init__(self, body: bytes, ct: str):
        self.content, self.status_code, self.headers, self.ok = body, 200, {"Content-Type": ct}, True

    def raise_for_status(self):
        return None

    def read(self):
        return self.content

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i + chunk_size]

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ct(url):
    return "image/png" if url.endswith(".png") else "image/jpeg"


def _cdn_small(url: str) -> bytes:
    """Cloudinary가 돌려줄 2000px JPEG — 측정 드라이버가 **다른 프로세스**에서 미리 만들어 둔 파일."""
    import hashlib
    return (CDN_DIR / ("cdn_" + hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg")).read_bytes()


def _patch_network():
    import requests
    import urllib.request
    real_get = requests.get

    def fake_get(url, *a, **k):
        u = str(url)
        if u.startswith("https://res.cloudinary.com/") and "/conv/" in u:
            from urllib.parse import unquote
            return _Resp(_cdn_small(unquote(u.split("/conv/", 1)[1])), "image/jpeg")
        if "alicdn.com" in u:
            return _Resp(_bytes(u), _ct(u))
        return real_get(url, *a, **k)
    requests.get = fake_get

    def fake_urlopen(req, *a, **k):
        u = req.full_url if hasattr(req, "full_url") else str(req)
        return _Resp(_bytes(u), _ct(u))
    urllib.request.urlopen = fake_urlopen
    try:
        import src.services.image_translate_tencent as T
        T._download = lambda url, proxies=None: _bytes(url)
    except Exception:                                      # noqa: BLE001
        pass
    try:
        import src.services.ocr_tencent as O
        O._call = lambda b64: {"TextDetections": [], "RequestId": "harness"}
        O.is_configured = lambda: True
    except Exception:                                      # noqa: BLE001
        pass
    try:
        import cloudinary.uploader as CU

        def fake_upload(src, **opts):
            if isinstance(src, str) and opts.get("format") == "jpg":
                from urllib.parse import quote
                return {"secure_url": "https://res.cloudinary.com/x/conv/" + quote(src, safe=""), "public_id": "c"}
            return {"secure_url": "https://res.cloudinary.com/x/1.jpg", "public_id": "1"}
        CU.upload = fake_upload
    except Exception:                                      # noqa: BLE001
        pass
    # 마켓 API(쿠팡·네이버 등) — 가짜 키로 부르되 네트워크에 나가지 않게 401 JSON(재시도 안 하는 응답 — 5xx면 스로틀 큐가 백오프로 14초 쥔다). 사진·Cloudinary만 위에서 흉내.
    real_req = requests.sessions.Session.request

    def fake_request(self, method, url, *a, **k):
        u = str(url)
        if "alicdn.com" in u or u.startswith("https://res.cloudinary.com/") or u.startswith("http://127.0.0.1"):
            if method.upper() == "GET":
                return fake_get(u)
            return real_req(self, method, url, *a, **k)
        r = requests.models.Response()
        r.status_code, r._content, r.url = 401, b'{"code":"UNAUTHORIZED","message":"blocked by z10c harness"}', u
        r.headers["Content-Type"] = "application/json"
        return r
    requests.sessions.Session.request = fake_request
    requests.request = lambda method, url, **k: fake_request(None, method, url, **k)
    try:
        from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
        import src.uploaders.naver_cdn_cache as CC
        CC.get = lambda *a, **k: None
        CC.put = lambda *a, **k: None
        CC.put_fail = lambda *a, **k: None
        SS._upload_parts = lambda self, parts: {"ok": True, "urls": [f"https://shop-phinf.pstatic.net/{i}.jpg"
                                                                      for i in range(len(parts))], "reason": ""}
    except Exception:                                      # noqa: BLE001
        pass


_patch_network()
from src.order_webhook import app  # noqa: E402
from src.seller_console import collect_history_store as _S  # noqa: E402

_extra = {"images": list(URLS), "detail_images": [], "title_ko": "블랙홀 접이식 수납 박스", "brand": "",
          "options": [{"name": "색상", "values": ["블랙", "그레이"]}], "category_code": "HOM"}
_iid = _S.append(source="extension", url="https://detail.tmall.com/item.htm?id=687", seller_id="default",
                 title="블랙홀 접이식 수납 박스", price="129", currency="CNY", extra=_extra)
ITEM_ID = _iid[0] if isinstance(_iid, tuple) else _iid


def _run_pv() -> dict:
    from src.services import coupang_image_check as C
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
    out = {}

    def judge():
        t0 = time.monotonic()
        r = C.check_url(URLS[0])
        out["cpx"] = {k: r.get(k) for k in ("state", "w", "h")}
        out["cpx_ms"] = int((time.monotonic() - t0) * 1000)

    def naver():
        t0 = time.monotonic()
        r = SS(account=None).cdn_map(URLS)
        out["naver"] = {"mapped": len(r["mapping"]), "dropped": len(r["dropped"])}
        out["naver_ms"] = int((time.monotonic() - t0) * 1000)
    th = [threading.Thread(target=judge), threading.Thread(target=naver)]
    [t.start() for t in th]
    [t.join() for t in th]
    return out


@app.get("/__z10c/item")
def _z10c_item():
    return {"item_id": ITEM_ID, "pid": os.getpid(), "url0": URLS[0]}


@app.get("/__z10c/product")
def _z10c_product():
    from src.seller_console.product_builder import build_product
    return build_product(_S.get(ITEM_ID, seller_id="default"), seller_id="default")


@app.post("/__z10c/pv")
def _z10c_pv():
    t0 = time.monotonic()
    out = _run_pv()
    out["ms"] = int((time.monotonic() - t0) * 1000)
    return out


@app.get("/__z10c/prodload")
def _z10c_prodload():
    """운영 워커가 하루를 돌며 올리는 모듈 — 상품명 정리(병음)·AI 호출(anthropic SDK)·DB 드라이버. 지연 import라 이 요청이 올린다."""
    import importlib.util
    from src.collectors import ko_polish
    ko_polish.romanize("北京故宫")
    if importlib.util.find_spec("anthropic"):
        import anthropic  # noqa: F401
    try:
        import psycopg  # noqa: F401
    except ImportError:
        pass
    time.sleep(0.3)                                        # 동시에 들어온 요청이 다른 워커로도 가게
    return {"pid": os.getpid()}


@app.get("/__z10c/rss")
def _z10c_rss():
    from src.utils import rss as R
    out = {"pid": os.getpid(), "rss": R.read_mb()[0]}
    if hasattr(R, "instance_mb"):                          # 후 코드에만 있다
        out.update(instance=R.instance_mb(), under_gunicorn=R.under_gunicorn(), start_ok=list(R.start_ok()))
    return out

