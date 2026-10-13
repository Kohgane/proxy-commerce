"""Z10-C 측정 — 로컬 gunicorn을 실제로 띄워 **인스턴스 합계**(master + 워커 전부 PSS 합)를 바깥에서 50ms마다 잰다.

    python scripts/z10c_measure.py <코드 폴더> <라벨> [workers threads]

- 코드 폴더 = 그 폴더의 코드·gunicorn.conf.py로 띄운다(전 = main 워크트리, 후 = 브랜치).
- workers/threads를 주면 env `GUNICORN_WORKERS`·`GUNICORN_MAX_WORKERS`·`GUNICORN_THREADS`로 넘긴다(운영 Render env 흉내).
- 앱 = `scripts/z10c_app.py`(이 스크립트 옆) — 바깥 호출만 막은 운영 앱 + 실제 BLACKHOLES 5장.
재는 것:
  1) base_boot: 뜬 직후 합계 · base_warm: 화면·요청 한 바퀴 돈 뒤(지연 import가 다 올라온 운영 상태) 합계
  2) 요청 경로별 피크: 요청 시작 직전 합계 → 요청(+뒤따르는 백그라운드 3초) 동안 최대 — 요청당 +MB (첫 번째·두 번째)
  3) 동시 2건: 사전검증 무거운 구간(`/__z10c/pv`) + 쿠팡 노출 미리보기(+대표 사진 판정)를 동시에 — 합계 피크
  4) 지연: 가벼운 화면 요청 160개를 동시 8개로 — p50·p95(ms). 혼자일 때 / 사전검증 1건이 같이 돌 때
결과는 JSON 한 줄(stdout 마지막 줄).
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = Path(sys.argv[1]).resolve()
LABEL = sys.argv[2]
WORKERS = sys.argv[3] if len(sys.argv) > 3 else ""
THREADS = sys.argv[4] if len(sys.argv) > 4 else ""
FIX = (HERE.parent / "tests/fixtures/realimages/blackholes").resolve()
CDN = Path(os.getenv("Z10C_CDN_DIR", "/tmp/z10c_cdn"))
#: Z10C_QUICK=1 — 테스트용: 뜬 직후·운영 상태 base + 동시 2건(사전검증 + 미리보기) 한 번만(요청 표·지연은 건너뛴다)
QUICK = os.getenv("Z10C_QUICK", "") == "1"


def _children(pid: int) -> list:
    out = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            st = open(f"/proc/{d}/stat").read()
            if int(st.rsplit(")", 1)[1].split()[1]) == pid:
                out.append(int(d))
        except (OSError, ValueError, IndexError):
            pass
    return out


def _kb(pid: int, path: str, key: str) -> int:
    try:
        for ln in open(f"/proc/{pid}/{path}"):
            if ln.startswith(key):
                return int(ln.split()[1])
    except OSError:
        pass
    return 0


class Inst:
    """master + 자식 전부의 PSS 합(MB) — 50ms 표본, 최대값 추적."""

    def __init__(self, master: int):
        self.master, self.peak, self.stop, self.cur = master, 0, False, 0
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def total(self) -> int:
        pids = [self.master] + _children(self.master)
        return sum(_kb(p, "smaps_rollup", "Pss:") for p in pids) // 1024

    def per_proc(self) -> dict:
        pids = [self.master] + _children(self.master)
        return {("master" if p == self.master else f"w{p}"): {"pss": _kb(p, "smaps_rollup", "Pss:") // 1024,
                                                             "rss": _kb(p, "status", "VmRSS:") // 1024} for p in pids}

    def _run(self):
        while not self.stop:
            self.cur = self.total()
            self.peak = max(self.peak, self.cur)
            time.sleep(0.05)

    def reset(self) -> int:
        self.cur = self.total()
        self.peak = self.cur
        return self.cur

    def settle(self, sec: float = 2.0) -> int:
        vals = []
        end = time.monotonic() + sec
        while time.monotonic() < end:
            vals.append(self.total())
            time.sleep(0.1)
        return int(statistics.median(vals))


def _prep_cdn():
    CDN.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(HERE))
    os.environ["Z10C_FIX"] = str(FIX)
    urls = [ln.split('"')[1] for ln in open(HERE / "z10c_app.py") if ln.strip().startswith('"https://img.alicdn.com')]
    for u in urls:
        out = CDN / ("cdn_" + hashlib.sha1(u.encode()).hexdigest()[:16] + ".jpg")
        if out.exists():
            continue
        tail = u.rsplit("/", 1)[-1]
        src = FIX / tail
        if not src.exists():
            src = sorted(FIX.glob(tail.split("~")[0].split("_!!")[0] + "*"))[0]
        subprocess.run([sys.executable, "-I", "-c",
                        "import sys;from PIL import Image;im=Image.open(sys.argv[1]);im.thumbnail((2000,2000));"
                        "bg=Image.new('RGB',im.size,(255,255,255));"
                        "bg.paste(im,mask=im.getchannel('A')) if im.mode=='RGBA' else bg.paste(im.convert('RGB'));"
                        "bg.save(sys.argv[2],'JPEG',quality=85)", str(src), str(out)], check=True)


def _port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http(base, path, method="GET", timeout=120, body=None):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(base + path, method=method, data=data,
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        body, code = e.read(), e.code
    return code, body, int((time.monotonic() - t0) * 1000)


def prevalidate(base, iid, product, markets=("coupang", "smartstore")) -> dict:
    """실제 사전검증 입구(`POST /seller/collect/prevalidate`) → 잡 폴링(0.5초)으로 끝까지. 마켓 API는 앱이 503으로 막혀 있다."""
    t0 = time.monotonic()
    code, b, _ms = http(base, "/seller/collect/prevalidate", "POST",
                        body={"product": product, "markets": list(markets), "item_id": iid})
    d = json.loads(b or b"{}")
    if code not in (200, 202) or not d.get("job_id"):
        return {"status": code, "body": d, "ms": int((time.monotonic() - t0) * 1000)}
    while time.monotonic() - t0 < 90:
        time.sleep(0.5)
        _c, jb, _m = http(base, f"/seller/collect/prevalidate/job/{d['job_id']}")
        j = json.loads(jb or b"{}")
        if j.get("state") in ("done", "failed", "error") and not j.get("pending"):
            break
    return {"status": code, "ms": int((time.monotonic() - t0) * 1000), "state": j.get("state"),
            "rows": [{k: (r or {}).get(k) for k in ("market", "ok", "verdict", "reason", "error")}
                     for r in (j.get("results") or [])][:4], "rss": j.get("rss"), "error": j.get("error")}


def main():
    _prep_cdn()
    port = _port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, Z10C_FIX=str(FIX), Z10C_CDN_DIR=str(CDN), PORT=str(port),
               GUNICORN_LOG_LEVEL="warning")
    for k in ("DATABASE_URL", "SUPABASE_DB_URL", "DATABASE_URL_DIRECT", "GOOGLE_SHEET_ID"):
        env.pop(k, None)
    if WORKERS:
        env.update(GUNICORN_WORKERS=WORKERS, GUNICORN_MAX_WORKERS=WORKERS)
    if THREADS:
        env["GUNICORN_THREADS"] = THREADS
    log = open(f"/tmp/z10c_{LABEL}.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "gunicorn", "z10c_app:app", "-c", str(CODE / "gunicorn.conf.py"),
                             "--pythonpath", str(HERE), "--bind", f"127.0.0.1:{port}"],
                            cwd=str(CODE), env=env, stdout=log, stderr=subprocess.STDOUT)
    res = {"label": LABEL, "code": str(CODE)}
    try:
        for _ in range(300):
            try:
                code, body, _ms = http(base, "/__z10c/item", timeout=2)
                if code == 200:
                    break
            except Exception:                              # noqa: BLE001
                pass
            time.sleep(0.2)
        info = json.loads(body)
        iid, url0 = info["item_id"], info["url0"]
        inst = Inst(proc.pid)
        time.sleep(1.0)
        res["workers"] = len(_children(proc.pid))
        res["base_boot_mb"] = inst.settle(2.0)
        res["procs_boot"] = inst.per_proc()

        from urllib.parse import quote
        paths = [
            ("편집 화면", "GET", f"/seller/collect/preview/{iid}"),
            ("쿠팡 노출 미리보기", "GET", f"/seller/m/item/{iid}/coupang-preview"),
            ("쿠팡 노출(편집 패널)", "GET", f"/seller/collect/{iid}/coupang-exposure"),
            ("대표 사진 판정(이미지 체크)", "GET", f"/seller/collect/{iid}/coupang-exposure/check?rep={quote(url0, safe='')}"),
            ("상품 마켓 상태", "GET", f"/seller/collect/{iid}/market-status"),
            ("마켓 현황", "GET", "/seller/market-status"),
            ("대시보드", "GET", "/seller/dashboard"),
            ("수집 목록", "GET", "/seller/collect/history"),
        ]
        rows = []
        for rnd in (() if QUICK else (1, 2)):
            for name, m, p in paths:
                b0 = inst.reset()
                code, _b, ms = http(base, p, m)
                time.sleep(3.0 if "판정" in name else 1.0)     # 대표 사진 판정은 백그라운드로 돈다 — 그 몫까지
                rows.append({"round": rnd, "name": name, "status": code, "ms": ms, "before_mb": b0,
                             "peak_mb": inst.peak, "delta_mb": inst.peak - b0})
        res["requests"] = rows
        res["base_warm_mb"] = inst.settle(3.0)
        res["procs_warm"] = inst.per_proc()
        # 운영 상태(병음·anthropic·psycopg가 워커마다 올라온 뒤) — 모든 워커가 한 번씩 받을 때까지
        seen = set()
        for _ in range(20):
            with ThreadPoolExecutor(4) as ex:
                for code, b, _ms in ex.map(lambda _k: http(base, "/__z10c/prodload"), range(4)):
                    seen.add(json.loads(b)["pid"])
            if len(seen) >= res["workers"]:
                break
        res["prodload_workers_hit"] = len(seen)
        res["base_prod_mb"] = inst.settle(3.0)
        res["procs_prod"] = inst.per_proc()

        if QUICK:   # 대표 사진 판정을 먼저 한 번(화면이 미리보기를 열 때처럼) — 안 하면 잡이 판정 대기로 마감까지 선다
            http(base, f"/seller/collect/{iid}/coupang-exposure/check?rep={quote(url0, safe='')}")
            time.sleep(3.0)
        _c, pb, _m = http(base, "/__z10c/product")
        product = json.loads(pb)
        b0 = inst.reset()
        real = prevalidate(base, iid, product)
        time.sleep(1.0)
        real.update(before_mb=b0, peak_mb=inst.peak, delta_mb=inst.peak - b0)
        res["prevalidate_alone"] = real

        conc = []
        for i in range(1 if QUICK else 3):
            b0 = inst.reset()
            out = {}

            def pv():
                out["real"] = prevalidate(base, iid, product)

            def prev():
                out["preview"] = http(base, f"/seller/m/item/{iid}/coupang-preview")
                out["check"] = http(base, f"/seller/collect/{iid}/coupang-exposure/check?rep={quote(url0, safe='')}")
            th = [threading.Thread(target=pv), threading.Thread(target=prev)]
            [t.start() for t in th]
            [t.join() for t in th]
            time.sleep(2.0)
            conc.append({"before_mb": b0, "peak_mb": inst.peak, "delta_mb": inst.peak - b0,
                         "prevalidate_ms": out["real"]["ms"], "prevalidate_state": out["real"]["state"],
                         "preview_status": out["preview"][0], "preview_ms": out["preview"][2]})
        res["concurrent"] = conc
        res["concurrent_peak_max_mb"] = max(c["peak_mb"] for c in conc)

        if QUICK:
            inst.stop = True
            return _finish(proc, res)
        # 지연 — ① 마켓 API를 안 부르는 화면 4종(워커·스레드 수 효과만) ② 쿠팡 노출 미리보기(쿠팡 API 2번 — 스로틀 큐가
        #   프로세스마다 초당 7번으로 페이싱한다: 워커 2개면 합쳐 14번(쿠팡 한도 10 초과), 1개면 7번. 줄 선 만큼 늦다)
        light = ["/seller/dashboard", "/seller/collect/history", f"/seller/collect/preview/{iid}",
                 f"/seller/collect/{iid}/market-status"]
        cpv = [f"/seller/m/item/{iid}/coupang-preview"]

        def burst(paths, n=160, conc_n=8):
            lat, per = [], {}
            with ThreadPoolExecutor(conc_n) as ex:
                for k, (code, _b, ms) in enumerate(ex.map(lambda k: http(base, paths[k % len(paths)]), range(n))):
                    lat.append(ms)
                    per.setdefault(paths[k % len(paths)].split("/")[-1], []).append(ms)
            lat.sort()
            pp = {k: {"p50": sorted(v)[len(v) // 2], "p95": sorted(v)[int(len(v) * 0.95) - 1]} for k, v in per.items()}
            return {"n": n, "p50": lat[len(lat) // 2], "p95": lat[int(len(lat) * 0.95) - 1], "max": lat[-1], "per_path": pp}
        res["latency_idle"] = burst(light)
        res["latency_coupang_preview"] = burst(cpv, n=40)
        bg = {}
        t = threading.Thread(target=lambda: bg.setdefault("pv", prevalidate(base, iid, product)))
        b0 = inst.reset()
        t.start()
        res["latency_with_pv"] = burst(light)
        t.join()
        res["latency_with_pv"]["inst_peak_mb"] = inst.peak
        res["latency_with_pv"]["pv_ms"] = bg["pv"]["ms"]
        inst.stop = True
    except BaseException:
        _stop(proc)
        raise
    return _finish(proc, res)


def _stop(proc):
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.kill()


def _finish(proc, res):
    _stop(proc)
    print(json.dumps(res, ensure_ascii=False))
    return res


if __name__ == "__main__":
    main()
