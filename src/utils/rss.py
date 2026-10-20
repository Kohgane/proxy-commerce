"""Z7(오너 2026-10-08) — 프로세스 메모리(RSS) 한 줄 로그. 다음 OOM 때 「어느 단계에서 커졌나」 좌표가 바로 나오게.

`/proc/self/status`의 VmRSS(지금)·VmHWM(이 프로세스 생애 최대)를 MB로 읽는다. 리눅스가 아니면 `resource`의
ru_maxrss(최대만)로 대신하고, 그것도 없으면 -1. 로그 형식: `[RSS] stage=<단계> rss_mb=<지금> peak_mb=<최대> …`.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("rss")


def read_mb() -> tuple:
    """`(rss_mb, peak_mb)` — 못 읽으면 -1."""
    try:
        cur = peak = -1
        with open("/proc/self/status", encoding="ascii", errors="ignore") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    cur = int(line.split()[1]) // 1024
                elif line.startswith("VmHWM:"):
                    peak = int(line.split()[1]) // 1024
        if cur >= 0:
            return cur, peak
    except OSError:
        pass
    try:
        import resource
        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) // 1024
        return -1, peak
    except Exception:                                      # noqa: BLE001
        return -1, -1


def log(stage: str, **kw) -> tuple:
    """단계 하나 — 로그 한 줄을 남기고 `(rss_mb, peak_mb)`를 돌려준다."""
    cur, peak = read_mb()
    try:
        if "job" not in kw and JOB.get():                 # Z10: 사전검증 잡 안이면 어느 잡인지 같은 줄에
            kw = {"job": JOB.get()[:8], **kw}
    except NameError:                                      # 모듈 로드 중(아래 정의 전)
        pass
    extra = " ".join(f"{k}={v}" for k, v in kw.items() if v not in (None, ""))
    logger.info("[RSS] stage=%s rss_mb=%d peak_mb=%d%s", stage, cur, peak, (" " + extra) if extra else "")
    return cur, peak


# ── Z10(오너 2026-10-10 22:29~22:35 KST OOM) — 단계 측정 · 잡 단위 상한 ─────────────────────────────────────────
#   실측: 네이버 사전검증 1건이 159 → 420MB(+261MB, 같은 시각 Render 512MB 초과 2회). 쿠팡은 159 → 181(peak 220).
#   단계마다 RSS·증감·소요 ms를 같은 줄에 남기고(`span`), 사전검증 잡 안에서는 RSS가 상한을 넘으면 **그 잡만** 멈춘다(`guard`).
import contextlib as _cl
import contextvars as _cv
import os as _os
import time as _time

#: 지금 도는 사전검증 잡 id(로그 줄·상한 판정용). 잡 밖(일반 요청)에서는 빈 값 — 상한을 적용하지 않는다.
JOB: "_cv.ContextVar[str]" = _cv.ContextVar("rss_job", default="")


# ── Z10-C(오너 2026-10-13 20:09 KST OOM) — 기준을 **인스턴스 합계**로 ─────────────────────────────────────────────────
#   실측(Z10-B 배포 뒤): pv_job_peak 301·308MB(base 158·162 + 잡 143·146) — 잡은 400 상한 아래였는데 Render 512MB 초과.
#   워커가 2개라 다른 워커(base 160 + 그쪽 요청)가 더해졌다. 그래서 잡·크론의 문지기는 **인스턴스 전체**를 본다:
#   - 새 잡·크론 시작: 합계 ≥ `INSTANCE_MEM_START_MAX_MB`(기본 420)면 거부(「메모리 여유 없음 — 잠시 후」)
#   - 진행 중인 잡: 합계 ≥ `INSTANCE_MEM_ABORT_MB`(기본 460)면 그 잡만 멈춘다(`guard`)
#   합계 = max(cgroup 익명 메모리(파일 캐시 제외), master + 워커 PSS 합). PSS는 preload로 공유된 페이지를
#   나눠 센다(RSS를 더하면 master·worker가 같은 페이지를 두 번 센다).

def _read_int(path: str) -> int:
    try:
        with open(path, encoding="ascii") as fh:
            return int(fh.read().strip().split()[0])
    except (OSError, ValueError, IndexError):
        return -1


def _stat_value(path: str, key: str) -> int:
    try:
        with open(path, encoding="ascii") as fh:
            for line in fh:
                k, _, v = line.partition(" ")
                if k == key:
                    return int(v)
    except (OSError, ValueError):
        pass
    return -1


def cgroup_mb() -> int:
    """cgroup **익명 메모리**(MB) — v2 `anon + shmem`, v1 `total_rss + total_shmem`. 파일 캐시는 빼고 본다(커널이 먼저
    돌려받는 몫이라 OOM 판정과 다르다 — 사용량 전체로 재면 캐시만으로 「여유 없음」이 된다). 못 읽으면 -1."""
    v2 = "/sys/fs/cgroup/memory.stat"
    anon = _stat_value(v2, "anon")
    if anon >= 0:
        return (anon + max(0, _stat_value(v2, "shmem"))) // (1024 * 1024)
    v1 = "/sys/fs/cgroup/memory/memory.stat"
    rss_ = _stat_value(v1, "total_rss")
    if rss_ >= 0:
        return (rss_ + max(0, _stat_value(v1, "total_shmem"))) // (1024 * 1024)
    return -1


def _pss_kb(pid) -> int:
    for path, key in ((f"/proc/{pid}/smaps_rollup", "Pss:"), (f"/proc/{pid}/status", "VmRSS:")):
        try:
            with open(path, encoding="ascii", errors="ignore") as fh:
                for line in fh:
                    if line.startswith(key):
                        return int(line.split()[1])
        except OSError:
            continue
    return -1


def _cmdline(pid) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return fh.read().replace(b"\0", b" ").decode("utf-8", "ignore")
    except OSError:
        return ""


def _children(pid) -> list:
    out = []
    try:
        for d in _os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                with open(f"/proc/{d}/stat", encoding="ascii", errors="ignore") as fh:
                    st = fh.read()
                ppid = int(st.rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                continue
            if ppid == int(pid):
                out.append(int(d))
    except OSError:
        pass
    return out


def under_gunicorn() -> bool:
    """이 프로세스가 gunicorn 워커인가 — 부모의 실행 파일·첫 인자(또는 프로세스 이름 `gunicorn: master`)에 gunicorn.
    (셸 명령 문자열 어딘가에 낱말이 들어 있는 것으로 판정하지 않는다.)"""
    try:
        with open(f"/proc/{_os.getppid()}/cmdline", "rb") as fh:
            argv = [a.decode("utf-8", "ignore") for a in fh.read().split(b"\0") if a][:2]
    except OSError:
        return False
    return any(_os.path.basename(a.split()[0] if a else "").startswith("gunicorn") for a in argv)


def family_pids() -> list:
    """메모리를 함께 세는 프로세스 — gunicorn 워커면 master + 그 자식 전부(다른 워커 포함), 아니면 이 프로세스만.
    (테스트·CI·개발 셸에서 같은 기계의 엉뚱한 프로세스를 세지 않는다.)"""
    me = _os.getpid()
    if under_gunicorn():
        master = _os.getppid()
        return [master] + _children(master)
    return [me]


def processes_pss_mb() -> int:
    """`family_pids()`의 PSS 합(MB) — preload로 공유한 페이지를 나눠 센다(RSS를 더하면 두 번 센다). 못 읽으면 -1."""
    vals = [_pss_kb(p) for p in family_pids()]
    vals = [v for v in vals if v >= 0]
    return sum(vals) // 1024 if vals else -1


def instance_mb() -> int:
    """인스턴스 메모리 합계 MB. gunicorn 아래(운영)면 max(cgroup 익명 메모리, master+워커 PSS 합) — 컨테이너엔 우리 프로세스만
    있다. 그 밖(테스트·개발)이면 이 프로세스 PSS만. 못 읽으면 이 프로세스 RSS."""
    vals = [processes_pss_mb()]
    if under_gunicorn() or _os.getenv("INSTANCE_MEM_SOURCE", "") == "cgroup":
        vals.append(cgroup_mb())
    vals = [v for v in vals if v >= 0]
    if vals:
        return max(vals)
    return read_mb()[0]


def _env_int(name: str, default: int) -> int:
    try:
        return int(_os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def start_limit_mb() -> int:
    """새 잡·크론을 시작하지 않는 인스턴스 합계(MB) — `INSTANCE_MEM_START_MAX_MB`(기본 420). 0이면 끈다."""
    return _env_int("INSTANCE_MEM_START_MAX_MB", 420)


def job_limit_mb() -> int:
    """진행 중인 잡을 멈추는 인스턴스 합계(MB) — `INSTANCE_MEM_ABORT_MB`(기본 460). 0이면 끈다.
    Z10-C: 예전엔 **프로세스** RSS 400(`PREVALIDATE_RSS_LIMIT_MB`)이었다 — 워커 2개 합으로 터지는 걸 못 막았다.
    옛 이름을 env에 둔 곳(대시보드·테스트)은 그 값을 그대로 쓴다(새 이름이 있으면 새 이름이 이긴다)."""
    if _os.getenv("INSTANCE_MEM_ABORT_MB", "").strip() == "" and _os.getenv("PREVALIDATE_RSS_LIMIT_MB", "").strip():
        return _env_int("PREVALIDATE_RSS_LIMIT_MB", 460)
    return _env_int("INSTANCE_MEM_ABORT_MB", 460)


def start_ok() -> tuple:
    """`(시작해도 되나, 합계 MB, 상한 MB)` — 새 잡·크론 문지기. 상한 0이거나 못 재면 통과."""
    lim = start_limit_mb()
    if lim <= 0:
        return True, -1, lim
    cur = instance_mb()
    if cur >= lim:
        # Y13-A(운영 실측 10-18: 인스턴스 바닥 413~414MB · 상한 420 — 일회성 작업·갱신 큐·사진 번역 깨우기가 줄줄이 「시작 거부」):
        #   놓았지만 운영체제에 안 돌려준 힙이 합계에 들어 있다 → gc + malloc_trim 한 번 하고 다시 잰다(상한은 그대로).
        try:
            import gc as _gc
            _gc.collect()
            from src.utils.render_worker import trim
            trim()
        except Exception:                                 # noqa: BLE001
            pass
        cur = instance_mb()
    return (cur < 0 or cur < lim), cur, lim


def release(reason: str = "") -> tuple:
    """Y14-2(오너 2026-10-20 「413MB 상시 점유」) — 일이 끝난 자리에서 gc + glibc `malloc_trim(0)`. `(전 MB, 후 MB)` 프로세스 RSS.

    로컬 실측: 앱 + 지연 모듈 147MB → 8스레드 큰 사진 작업 직후 697MB → **gc만으로는 697 그대로** → malloc_trim 뒤 187MB.
    놓은 힙을 운영체제에 안 돌려주면 그 자리가 다음 일까지 「상시 점유」로 남는다(그리기 워커·네이버 업로드만 하고 있었다).
    백그라운드 워커 한 회차 끝(`workers.record_run`) · 사전검증 잡 끝 · 마켓 등록 끝에서 부른다. 실패해도 일은 계속.

    `RSS_RELEASE=0`이면 아무것도 안 한다 — 테스트 프로세스(conftest)용: 전체 스위트는 힙이 수 GB라, 앞 테스트가 띄운 잡 스레드의
    `gc.collect()`가 1초 넘게 GIL을 쥐고 다음 테스트의 벽시계 계약(「1초 안에」)을 깼다(Y14 · test_z9 두 건). 운영 기본은 켬."""
    if _os.getenv("RSS_RELEASE", "1") == "0":
        return 0, 0
    try:
        import gc as _gc
        before = read_mb()[0]
        _gc.collect()
        from src.utils.render_worker import trim
        trim()
        after = read_mb()[0]
        if before - after >= 20:
            logger.info("[RSS] stage=release reason=%s before_mb=%d after_mb=%d", reason[:40], before, after)
        return before, after
    except Exception:                                     # noqa: BLE001
        return -1, -1


BUSY_MESSAGE = "메모리 여유 없음 — 잠시 후 다시 눌러 주세요"


class MemoryCapExceeded(RuntimeError):
    """사전검증 잡이 메모리 상한을 넘었다 — 잡만 멈추고(카드에 원문) 워커·서비스는 살린다."""

    def __init__(self, stage: str, rss_mb: int, limit_mb: int, detail: str = ""):
        self.stage, self.rss_mb, self.limit_mb, self.detail = stage, rss_mb, limit_mb, detail
        super().__init__(f"메모리 상한 — {stage}에서 인스턴스 합계 {rss_mb}MB(상한 {limit_mb}MB){(' · ' + detail) if detail else ''}")


def guard(stage: str, detail: str = "") -> None:
    """사전검증 잡 안에서만: RSS가 상한을 넘었으면 `MemoryCapExceeded`. 잡 밖이면 아무것도 안 한다."""
    if not JOB.get():
        return
    lim = job_limit_mb()
    if lim <= 0:
        return
    cur = instance_mb()                                   # Z10-C: 인스턴스 합계
    if cur <= lim:
        # Z10-B: 경계 사이에 넘었다가 내려왔어도(샘플러가 봤다) 이 잡은 멈춘다 — 다음 장에서 또 넘는다
        from src.utils import rss_sampler as _smp
        hit = _smp.over(JOB.get())
        if hit:
            cur = hit[0]
            detail = (detail + " · " if detail else "") + f"샘플러가 {hit[2]}ms에 {hit[0]}MB를 봤어요"
    if cur > lim:
        log("cap_exceeded", job=JOB.get()[:8], at=stage, limit_mb=lim, detail=detail)
        raise MemoryCapExceeded(stage, cur, lim, detail)


@_cl.contextmanager
def span(stage: str, **kw):
    """한 단계 — 끝날 때 `[RSS] stage=… rss_mb=… delta_mb=… ms=… job=…` 한 줄. `kw`(장수·바이트 등)는 안에서 채울 수 있게 dict로 넘긴다."""
    before, _p = read_mb()
    t0 = _time.monotonic()
    box = dict(kw)
    try:
        yield box
    finally:
        cur, _peak = read_mb()
        log(stage, delta_mb=(cur - before) if cur >= 0 and before >= 0 else "",
            ms=int((_time.monotonic() - t0) * 1000), **box)
