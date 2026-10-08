"""src/utils/perf.py — 요청 구간 타이밍(쿼리·렌더·총) 측정.

`perf_block("db")`로 감싼 구간의 누적 시간을 flask.g에 모으고, request_logger가 로그와
Server-Timing 헤더로 노출한다(브라우저 네트워크 탭에서 구간 확인). 병목을 수치로 증명하기 위함.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

try:
    from flask import g, has_request_context
except Exception:  # flask 없는 컨텍스트(테스트 등)
    g = None

    def has_request_context():
        return False


_ATTR = "_kgp_perf"


def _bucket() -> dict:
    if not has_request_context():
        return {}
    d = getattr(g, _ATTR, None)
    if d is None:
        d = {}
        setattr(g, _ATTR, d)
    return d


@contextmanager
def perf_block(name: str):
    """이 블록의 경과 시간(ms)을 name 버킷에 누적한다(중첩·반복 호출 합산)."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt = (time.perf_counter() - t0) * 1000.0
        b = _bucket()
        if b is not None:
            b[name] = round(b.get(name, 0.0) + dt, 2)


_CNT_ATTR = "_kgp_perf_count"


def _counter() -> dict:
    if not has_request_context():
        return {}
    d = getattr(g, _CNT_ATTR, None)
    if d is None:
        d = {}
        setattr(g, _CNT_ATTR, d)
    return d


def perf_count(name: str, n: int = 1) -> None:
    """이벤트 카운트(예: DB 쿼리·연결 수) — N+1 진단용."""
    c = _counter()
    if c is not None:
        c[name] = c.get(name, 0) + n


def perf_counts() -> dict:
    c = _counter()
    return dict(c) if c else {}


_MS_ATTR = "_kgp_perf_ms"
_MS_CAP = 50   # 요청당 기록할 개별 쿼리 ms 최대 개수(폭주 방지)


def perf_add_ms(name: str, ms: float) -> None:
    """개별 이벤트(예: DB 쿼리 1건)의 ms를 리스트로 누적 — 요청당 [개별 ms] 진단용."""
    if not has_request_context():
        return
    d = getattr(g, _MS_ATTR, None)
    if d is None:
        d = {}
        setattr(g, _MS_ATTR, d)
    lst = d.setdefault(name, [])
    if len(lst) < _MS_CAP:
        lst.append(round(float(ms), 2))


def perf_ms_list(name: str) -> list:
    if not has_request_context():
        return []
    d = getattr(g, _MS_ATTR, None)
    return list(d.get(name, [])) if d else []


def perf_snapshot() -> dict:
    """현재까지 누적된 구간 타이밍(ms) 스냅샷."""
    b = _bucket()
    return dict(b) if b else {}


def perf_server_timing() -> str:
    """Server-Timing 헤더 값(예: 'db;dur=12.3, render;dur=45.6')."""
    b = perf_snapshot()
    if not b:
        return ""
    return ", ".join(f"{k};dur={v}" for k, v in b.items())


# ---------------------------------------------------------------------------
# 외부 호출 계측 (F21-3)
# ---------------------------------------------------------------------------
# 왜 경계에서 재나: F21-4 선조사에서 **짐작한 원인 셋이 다 아니었다**
#   (대시보드 진단은 env만 읽고, 부팅 훅은 요청 경로에 없고, F18 카운터는 텔레그램 전용).
#   원인을 모르는 채로 "아는 자리"만 계측하면, 모르는 자리는 영영 안 보인다.
#   그래서 `requests` 어댑터 한 겹에서 **전부** 센다 — 공용 래퍼가 없기 때문이다.
#
# 이 겹은 **재기만 한다.** 요청을 바꾸지도, 막지도, 재시도하지도 않는다.
# 계측이 터져도 호출은 그대로 간다(그래서 안팎이 try로 감싸여 있다).

_EXT_HOSTS_ATTR = "_kgp_perf_ext_hosts"
_EXT_MS_ATTR = "_kgp_perf_ext_ms"
_EXT_HOST_CAP = 20
_probe_installed = False


def perf_note_external(host: str, ms: float) -> None:
    """외부 호출 1건 — 구간 누적 + 건수 + 호스트(어디로 나갔는지) + 호스트별 누적 ms(Z9)."""
    if not has_request_context():
        return
    b = _bucket()
    if b is not None:
        b["external"] = round(b.get("external", 0.0) + float(ms), 2)
    perf_count("external_call")
    d = getattr(g, _EXT_HOSTS_ATTR, None)
    if d is None:
        d = []
        setattr(g, _EXT_HOSTS_ATTR, d)
    if len(d) < _EXT_HOST_CAP:
        d.append(str(host or "?"))
    # Z9(오너 2026-10-09): 호스트 이름만으론 「어디서 시간을 먹었나」를 못 읽는다 — 호스트별 누적 ms·건수.
    m = getattr(g, _EXT_MS_ATTR, None)
    if m is None:
        m = {}
        setattr(g, _EXT_MS_ATTR, m)
    key = str(host or "?")
    if key not in m and len(m) >= _EXT_HOST_CAP:
        key = "(그 밖)"                       # 호스트가 많아도 시간은 버리지 않는다 — 넘친 것은 한데 합산
    cur = m.get(key) or [0.0, 0]
    m[key] = [round(cur[0] + float(ms), 1), cur[1] + 1]


def perf_external_hosts() -> list:
    if not has_request_context():
        return []
    return list(getattr(g, _EXT_HOSTS_ATTR, None) or [])


def perf_external_ms_by_host() -> dict:
    """`{host: [누적 ms, 건수]}` — 요청(또는 같은 g를 쓰는 잡) 동안."""
    if not has_request_context():
        return {}
    return {k: list(v) for k, v in (getattr(g, _EXT_MS_ATTR, None) or {}).items()}


import threading as _threading

_TL = _threading.local()
_u3_probe_installed = False


def install_external_probe() -> bool:
    """`requests` 어댑터에 계측 겹을 한 번 씌운다(멱등). 씌웠으면 True.

    `requests`가 없거나 내부 구조가 바뀌면 **조용히 포기**한다 —
    계측이 서비스를 막는 일은 없어야 한다.
    """
    global _probe_installed
    if _probe_installed:
        return True
    try:
        from requests.adapters import HTTPAdapter
    except Exception:
        return False
    if getattr(HTTPAdapter.send, "_kgp_probed", False):
        _probe_installed = True
        return True

    _orig = HTTPAdapter.send

    def _send(self, request, *a, **kw):
        t0 = time.perf_counter()
        _TL.in_requests = getattr(_TL, "in_requests", 0) + 1      # urllib3 겹이 같은 호출을 두 번 세지 않게
        try:
            return _orig(self, request, *a, **kw)
        finally:
            _TL.in_requests -= 1
            try:
                from urllib.parse import urlparse
                perf_note_external(urlparse(getattr(request, "url", "") or "").hostname or "?",
                                   (time.perf_counter() - t0) * 1000.0)
            except Exception:
                pass

    _send._kgp_probed = True
    HTTPAdapter.send = _send
    _probe_installed = True
    return True


def install_urllib3_probe() -> bool:
    """Z9 — `requests`를 거치지 않고 **urllib3를 직접** 쓰는 SDK(Cloudinary 등)도 외부 호출로 센다(재기만 한다).

    01:21 KST 사전검증 25초 중 ~21초가 어느 계측에도 안 잡혔다 — `requests` 겹 밖의 호출은 보이지 않았다.
    `requests`가 부른 urllib3 호출은 위 겹이 이미 셌으니 건너뛴다(스레드 표시).
    """
    global _u3_probe_installed
    if _u3_probe_installed:
        return True
    try:
        from urllib3.connectionpool import HTTPConnectionPool
    except Exception:
        return False
    if getattr(HTTPConnectionPool.urlopen, "_kgp_probed", False):
        _u3_probe_installed = True
        return True
    _orig = HTTPConnectionPool.urlopen

    def _urlopen(self, method, url, *a, **kw):
        if getattr(_TL, "in_requests", 0):
            return _orig(self, method, url, *a, **kw)
        t0 = time.perf_counter()
        try:
            return _orig(self, method, url, *a, **kw)
        finally:
            try:
                perf_note_external(str(getattr(self, "host", "") or "?") + "(urllib3)",
                                   (time.perf_counter() - t0) * 1000.0)
            except Exception:
                pass

    _urlopen._kgp_probed = True
    HTTPConnectionPool.urlopen = _urlopen
    _u3_probe_installed = True
    return True
