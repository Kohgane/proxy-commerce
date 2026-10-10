"""Z10-B 재현 하네스 — **실제 BLACKHOLES 갤러리 5장**(픽스처)으로 사전검증 앞 구간·이미지 저장본 크론의 RSS 피크.

    python scripts/z10b_measure.py <픽스처 폴더> <pv|cron|cron-fallback>

픽스처 폴더: `tests/fixtures/realimages/blackholes/` — 파일 이름이 원본 URL의 마지막 조각(`O1CN01…_!!3596090318.png` 등).
alicdn 대신 그 파일을 돌려준다(가짜 이미지로 재지 않는다 — 오너 2026-10-11). 마켓·Cloudinary·텐센트 호출은 막는다(응답만 흉내).
실행하는 코드 = 현재 작업 폴더(cwd) — main 워크트리에서 돌리면 「전」, 브랜치에서 돌리면 「후」.
측정: 50ms마다 VmRSS(이 프로세스) — 기준(시작 직전)·피크·피크−기준. 장마다 한 줄(가로×세로·형식·바이트)도 찍는다.

pv   = 02:24:30~33 구간에 같이 도는 것: `cpx-check`(쿠팡 대표 사진 판정 — 1번 장, 흰 배경 + OCR 줄이기) +
       네이버 상세 사전 올리기 `cdn_map`(5장 받기 → 묶음 업로드 흉내). 둘을 **동시에**(실제처럼 다른 스레드).
cron = `/cron/image-copies` 한 회전(그 상품 5장). 전: `process_image`(받아 풀어 가공) · 후: 원격 업로드(URL만).
cron-fallback = 후 코드에서 Cloudinary가 원격으로 못 받는 경우(직접 받아 올림 폴백).
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.getcwd())
FIX = Path(sys.argv[1]).resolve()
MODE = sys.argv[2] if len(sys.argv) > 2 else "pv"
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
    if not hits:
        raise SystemExit(f"픽스처 없음: {tail} (폴더 {FIX})")
    return hits[0]


def _bytes(url: str) -> bytes:
    return _file_for(url).read_bytes()


def rss_mb() -> int:
    with open("/proc/self/status") as fh:
        for ln in fh:
            if ln.startswith("VmRSS:"):
                return int(ln.split()[1]) // 1024
    return -1


class Sampler:
    def __init__(self):
        self.base, self.peak, self.stop = rss_mb(), rss_mb(), False
        self.t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self.stop:
            self.peak = max(self.peak, rss_mb())
            time.sleep(0.05)

    def __enter__(self):
        self.t.start()
        return self

    def __exit__(self, *a):
        self.stop = True
        self.t.join(1)
        self.peak = max(self.peak, rss_mb())


class _Resp:
    def __init__(self, body: bytes, ct: str):
        self.content, self.status_code, self.headers = body, 200, {"Content-Type": ct}

    def raise_for_status(self):
        return None

    def read(self):
        return self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ct(url):
    return "image/png" if url.endswith(".png") else "image/jpeg"


def patch_network():
    import requests
    import urllib.request
    real_get = requests.get

    def fake_get(url, *a, **k):
        if "alicdn.com" in str(url):
            return _Resp(_bytes(str(url)), _ct(str(url)))
        return real_get(url, *a, **k)
    requests.get = fake_get

    def fake_urlopen(req, *a, **k):
        u = req.full_url if hasattr(req, "full_url") else str(req)
        return _Resp(_bytes(u), _ct(u))
    urllib.request.urlopen = fake_urlopen
    try:                                                   # 텐센트 이미지 받기(대표 사진 판정)
        import src.services.image_translate_tencent as T
        T._download = lambda url, proxies=None: _bytes(url)
    except Exception:
        pass
    try:                                                   # 텐센트 OCR 호출 → 빈 응답
        import src.services.ocr_tencent as O
        O._call = lambda b64: {"TextDetections": [], "RequestId": "harness"}
        O.is_configured = lambda: True
    except Exception:
        pass
    try:                                                   # Cloudinary 업로드 → 받은 것의 크기만 기록
        import cloudinary.uploader as CU
        sent = []

        def fake_upload(src, **opts):
            n = len(src.getvalue()) if hasattr(src, "getvalue") else 0
            sent.append({"remote": isinstance(src, str), "bytes": n})
            return {"secure_url": f"https://res.cloudinary.com/x/{len(sent)}.jpg", "public_id": str(len(sent)), "bytes": n}
        CU.upload = fake_upload
        globals()["SENT"] = sent
    except Exception:
        pass


def describe():
    from PIL import Image
    for u in URLS:
        b = _bytes(u)
        with Image.open(io.BytesIO(b)) as im:
            print(f"  장: {u.rsplit('/', 1)[-1][:40]} {im.format} {im.size[0]}×{im.size[1]} mode={im.mode} {len(b):,}B")


def run_pv():
    from src.services import coupang_image_check as C
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
    import src.uploaders.naver_cdn_cache as CC
    CC.get = lambda *a, **k: None
    CC.put = lambda *a, **k: None
    CC.put_fail = lambda *a, **k: None
    SS._upload_parts = lambda self, parts: {"ok": True, "urls": [f"https://shop-phinf.pstatic.net/{i}.jpg" for i in range(len(parts))], "reason": ""}
    os.environ["COUPANG_IMAGE_CHECK"] = "1"
    out = {}

    def judge():
        t0 = time.monotonic()
        out["cpx"] = C.check_url(URLS[0])
        out["cpx_ms"] = int((time.monotonic() - t0) * 1000)

    def naver():
        t0 = time.monotonic()
        r = SS(account=None).cdn_map(URLS)
        out["naver"] = {"mapped": len(r["mapping"]), "dropped": len(r["dropped"])}
        out["naver_ms"] = int((time.monotonic() - t0) * 1000)
    with Sampler() as s:
        th = [threading.Thread(target=judge), threading.Thread(target=naver)]
        [t.start() for t in th]
        [t.join() for t in th]
    cpx = out.get("cpx") or {}
    print(json.dumps({"mode": "pv", "base_mb": s.base, "peak_mb": s.peak, "delta_mb": s.peak - s.base,
                      "cpx": {k: cpx.get(k) for k in ("state", "w", "h", "white_pct", "decode_why", "why")},
                      "cpx_ms": out.get("cpx_ms"), "naver": out.get("naver"), "naver_ms": out.get("naver_ms")},
                     ensure_ascii=False))


def run_cron(fallback: bool):
    import src.api.extension_api as ea
    ea._cdn_configured = lambda: True
    os.environ.update(CLOUDINARY_CLOUD_NAME="x", CLOUDINARY_API_KEY="x", CLOUDINARY_API_SECRET="x")
    if fallback:
        import cloudinary.uploader as CU
        real = CU.upload

        def no_remote(src, **opts):
            if isinstance(src, str):
                raise RuntimeError("Error in loading " + src[:60] + " - 403 Forbidden")
            return real(src, **opts)
        CU.upload = no_remote
    t0 = time.monotonic()
    with Sampler() as s:
        r = ea._store_image_copies(list(URLS), item_id="301c02cd", budget_sec=45)
        ms = int((time.monotonic() - t0) * 1000)
        time.sleep(float(os.getenv("Z10B_TAIL_SEC", "8")))   # 전 코드: 버린 스레드가 크론 뒤에도 돈다 — 그 메모리까지 표본에
    print(json.dumps({"mode": "cron" + ("-fallback" if fallback else ""), "base_mb": s.base, "peak_mb": s.peak,
                      "delta_mb": s.peak - s.base, "ms": ms,
                      "note": r.get("images_stored_note"), "uploads": globals().get("SENT")}, ensure_ascii=False))


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)
    patch_network()
    describe()
    if MODE == "pv":
        run_pv()
    else:
        run_cron(MODE == "cron-fallback")
    time.sleep(0.3)        # 버린 스레드(전 코드)가 끝까지 돌며 쥐는 메모리도 표본에 — 아래 한 번 더
    print(json.dumps({"after_300ms_rss_mb": rss_mb(), "threads_alive": threading.active_count()}))
