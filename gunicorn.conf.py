import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
# I/O 바운드(Google Sheets/마켓 API 왕복)라 gthread로 동시성↑ — 워커당 스레드로 블로킹 호출 겹치기 (v8 속도).
# Z10-C(오너 2026-10-13 20:09 KST OOM — Render 512MB): 워커 2개 × (base 160 + 사전검증 잡 146 + 동시 요청) > 512.
#   잡 하나는 상한 아래였고 **합계**가 넘었다 → 워커 1개 · 스레드 8(gthread). 사전검증 1개 + 요청 동시 처리는 스레드로.
#   Render 대시보드에 예전 값 `GUNICORN_WORKERS=2`가 남아 있어도 `GUNICORN_MAX_WORKERS`(기본 1)로 묶는다 —
#   플랜을 올리면(Standard 2GB) 그때 `GUNICORN_MAX_WORKERS`를 올린다.
workers = max(1, min(int(os.getenv('GUNICORN_WORKERS', '1') or 1), int(os.getenv('GUNICORN_MAX_WORKERS', '1') or 1)))
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'gthread')
threads = int(os.getenv('GUNICORN_THREADS', '8'))
# 순찰 77: gthread에선 이 값이 **요청 상한이 아니다** — 본 스레드가 1초마다 마스터에 살아 있다고 알려서, 요청 스레드가 전부 묶여도
#   워커는 안 죽는다. 묶인 풀은 `restart_log.check_quiet`(요청 0건 10분 + 처리 중 HTTP ≥ 스레드 수 → 이 워커만 내림)가 맡는다.
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))
# Z7(오너 2026-10-08 OOM): 워커 2개 이상이면 요청 200±50번마다 워커를 갈아끼운다 — 누수 보험(한 워커가 커져도 오래 안 간다).
#   워커 1개면 재시작 순간 받을 곳이 없으므로 켜지 않는다. 0을 주면 끈다.
max_requests = int(os.getenv('GUNICORN_MAX_REQUESTS', '200')) if workers >= 2 else 0
max_requests_jitter = int(os.getenv('GUNICORN_MAX_REQUESTS_JITTER', '50')) if workers >= 2 else 0
# P0-운영(오너 2026-10-23): 20 이하 — Render가 새 인스턴스로 넘기는 동안 옛 인스턴스가 오래 붙잡지 않게.
graceful_timeout = min(20, int(os.getenv('GUNICORN_GRACEFUL_TIMEOUT', '20') or 20))
keepalive = int(os.getenv('GUNICORN_KEEPALIVE', '5'))
accesslog = '-'
# M3-iOS 실측 결함(2026-09-28): 기본 형식의 `%(r)s`(요청 줄)·`%(f)s`(Referer)는 **쿼리를 통째로** 남긴다 —
#   공유 시트 `/seller/collect/share?url=…?tk=…`의 `tk`가 접근 로그에 새고 있었다. 경로(`%(U)s`)만 남긴다.
#   쿼리는 앱 요청 로그(`request_logger._safe_query`)가 스크럽해서 남긴다. start_render.sh와 같은 값.
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(M)sms "%(a)s"'
errorlog = '-'
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')
preload_app = True

# P0-운영(오너 2026-10-23 Render 로그 — 10-23 09:10 UTC vssjj): 마스터가 「Shutting down: Master」를 찍고도 안 끝났다.
#   preload라 앱 임포트가 **마스터**에서 일어나, 임포트 때 띄우던 상시 스레드(틱 공백 감시·이미지 번역 자동·폴러·부팅 실측 등)가
#   전부 마스터에 붙었고 — 그 안의 스레드 풀 일이 인터프리터 종료를 붙잡았다(로컬 재현: 풀 일 하나로 마스터가 20초+ 생존).
#   ① 임포트 때는 띄우지 않는다(`KGP_DEFER_BG_THREADS`) → 워커가 뜬 뒤(`post_worker_init`) 그 워커에서 띄운다. 마스터는 감독만.
#   ② 내려갈 때: 멈춤 신호 + join(합계 몇 초) → 그래도 붙잡혀 있으면 `os._exit`(워커 4초 · 마스터 2초).
os.environ.setdefault('KGP_DEFER_BG_THREADS', '1')


# 순찰 106-A(오너 2026-10-26 「메모리 바닥」): preload라 앱 객체는 마스터 페이지에 있고 워커는 그걸 나눠 쓴다(CoW).
#   워커의 gc가 세대 2를 훑을 때마다 객체 머리(gc 헤더)에 써서 그 페이지가 워커 쪽으로 복사된다 → 마스터 사본 + 워커 사본 = 두 번 센다.
#   포크 직전에 지금 객체를 영구 세대로 옮긴다(`gc.freeze`) — gc가 다시 훑지 않아 공유가 유지된다(로컬 실측 합계 101→83MB).
#   `KGP_GC_FREEZE=0`이면 끈다.
def pre_fork(server, worker):
    if os.getenv('KGP_GC_FREEZE', '1') == '0':
        return
    try:
        import gc as _gc
        _gc.collect()
        _gc.freeze()
    except Exception as exc:                                     # noqa: BLE001 — 얼리기 실패가 포크를 막지 않는다
        server.log.warning('[부팅] gc.freeze 실패(계속): %s', exc)


def post_worker_init(worker):
    try:
        import src.order_webhook as _app_mod
        _app_mod.start_background_threads()
    except Exception as exc:                                     # noqa: BLE001 — 백그라운드 실패가 요청 처리를 막지 않는다
        worker.log.warning('[부팅] 백그라운드 스레드 시작 실패(계속): %s', exc)
    # 순찰 73: 새 워커가 떴다 — 직전 종료 기록과 짝지어 재시작에 걸린 시간 · 우리 상한 밖 재시작(배포·Render)인지(`rss:restart`)
    try:
        from src.utils import restart_log as _rl
        _cfg = getattr(worker, 'cfg', None)
        _rl.note_boot(os.getpid(), _worker_rss_mb(), threads=getattr(_cfg, 'threads', None), timeout=getattr(_cfg, 'timeout', None),
                      worker_class=str(getattr(_cfg, 'worker_class_str', '') or ''), workers=getattr(_cfg, 'workers', None))
        _rl.arm_no_traffic()                                     # 순찰 106-F: 부팅 60초 안 요청 0이면 `no_traffic` 한 줄
    except Exception as exc:                                     # noqa: BLE001
        worker.log.warning('[부팅] 재시작 기록 실패(계속): %s', exc)


def _arm_hard_exit(sec, log):
    """이 파일 안에서만 — 앱 모듈을 못 읽어도(임포트 실패·경로) 강제 종료는 건다."""
    import threading as _th
    import time as _tm

    def _kill():
        _tm.sleep(sec)
        try:
            log.warning('[종료] %.1f초 뒤에도 프로세스가 안 끝남 — 강제 종료(pid %s)', sec, os.getpid())
        except Exception:                                        # noqa: BLE001
            pass
        os._exit(0)

    _th.Thread(target=_kill, name='hard-exit', daemon=True).start()


def _stop_app_threads(join_sec, log):
    try:
        from src.utils import shutdown as _sd
        _sd.stop_all(join_sec=join_sec)
    except Exception as exc:                                     # noqa: BLE001
        log.warning('[종료] 앱 스레드 멈춤 신호 실패(강제 종료는 건다): %s', exc)


def worker_exit(server, worker):
    _stop_app_threads(3.0, worker.log)
    _arm_hard_exit(4.0, worker.log)


def on_exit(server):
    _stop_app_threads(1.0, server.log)
    _arm_hard_exit(2.0, server.log)

# Z10-C: 워커 1개에선 이 재시작이 서비스를 잠깐 비운다 — 잡·크론이 없을 때만(아래 `_active_jobs`) · 같은 상한.
# Z10(오너 2026-10-10 22:34·22:35 KST — Render 512MB 초과 2회): 워커 RSS 상한 — 요청이 끝났는데 이 워커가
#   `WORKER_RSS_LIMIT_MB`(기본 380)를 넘었으면 **이 워커만** 조용히 갈아끼운다(받던 요청은 끝내고 나간다).
#   두 워커가 동시에 넘으면 서비스 전체가 비므로, 다른 워커가 최근 `WORKER_RSS_RESTART_GAP_SEC`(60초) 안에 나갔으면 기다린다.
_RSS_LIMIT_MB = int(os.getenv('WORKER_RSS_LIMIT_MB', '380') or 0)
_RSS_GAP_SEC = int(os.getenv('WORKER_RSS_RESTART_GAP_SEC', '60') or 60)
_RSS_STAMP = os.getenv('WORKER_RSS_RESTART_STAMP', '/tmp/kgp_worker_rss_restart')


def _worker_rss_mb():
    try:
        with open('/proc/self/status', encoding='ascii', errors='ignore') as fh:
            for line in fh:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return -1


def _active_jobs():
    """지금 이 워커에서 도는 사전검증 잡·크론 이름(샘플러 `watch` 구간). 못 읽으면 빈 목록."""
    try:
        from src.utils import rss_sampler
        return rss_sampler.active_names()
    except Exception:
        return []


# Y15(운영 10-21 17:20~10-22 07:10 — 14시간): 새 잡 문지기는 **인스턴스 합계**(master+워커, `INSTANCE_MEM_START_MAX_MB` 420)로 보고
#   이 재시작은 **워커 RSS**(380)만 봤다. 워커 340MB · 합계 422~435MB에서 문지기는 매 틱 「시작 거부」, 재시작은 「상한 아래」 —
#   일회성 작업 54줄이 밤새 하나도 안 돌았다(서로 풀어 줄 쪽이 없는 교착). 합계가 문지기 상한 이상이면 같은 조건(잡 없음·간격)으로 갈아끼운다.
#   합계 재기는 /proc을 여러 번 읽으므로 `_INST_EVERY_SEC`(60초)에 한 번만.
_INST_EVERY_SEC = int(os.getenv('WORKER_INSTANCE_CHECK_SEC', '60') or 60)
_inst_seen = {'at': 0.0, 'over': False, 'mb': -1, 'lim': 0}


def _instance_over():
    """`(인스턴스 합계 ≥ 새 잡 문지기 상한, 합계 MB, 상한 MB)` — 60초에 한 번 잰다. 못 재면 아니오."""
    import time as _t
    now = _t.time()
    if now - _inst_seen['at'] < _INST_EVERY_SEC:
        return _inst_seen['over'], _inst_seen['mb'], _inst_seen['lim']
    over, mb, lim = False, -1, 0
    try:
        from src.utils import rss as _rss
        lim = _rss.start_limit_mb()
        if lim > 0:
            mb = _rss.instance_mb()
            over = mb >= lim
    except Exception:
        pass
    _inst_seen.update(at=now, over=over, mb=mb, lim=lim)
    return over, mb, lim


# 순찰 106-A2(운영 10-26): 일 몰린 뒤 합계가 350MB에 12시간 붙어 있었다 — 문지기(420)·워커 상한(380) 아래라 아무도 안 갈아끼웠다.
#   틱이 `rss.note_idle_floor`로 「일 없이 높은 틱」을 세고, 이어진 수가 차면 여기서 같은 길(잡 없음·간격)로 갈아끼운다.
#   마스터 몫이면 갈아끼워도 안 내려가니 `INSTANCE_IDLE_RECYCLE_GAP_SEC`(6시간)에 한 번만 — 매 요청 갈아끼우는 고리 방지.
_IDLE_STAMP = os.getenv('INSTANCE_IDLE_RECYCLE_STAMP', '/tmp/kgp_idle_recycle')
_IDLE_GAP_SEC = int(os.getenv('INSTANCE_IDLE_RECYCLE_GAP_SEC', '21600') or 21600)


def _idle_floor_due():
    """`(갈아끼울 때인가, 사유 꼬리)` — 못 재면 아니오."""
    try:
        from src.utils import rss as _rss
        due, mb, n = _rss.idle_recycle_due()
    except Exception:
        return False, ''
    if not due:
        return False, ''
    import time as _t
    try:
        if _t.time() - os.path.getmtime(_IDLE_STAMP) < _IDLE_GAP_SEC:
            return False, ''
    except OSError:
        pass
    return True, f' · 쉬는 동안 합계 {mb} ≥ {_rss.idle_recycle_mb()} ({n}틱 연속)'


def post_request(worker, req, environ, resp):
    if _RSS_LIMIT_MB <= 0 or not getattr(worker, 'alive', False):
        return
    rss = _worker_rss_mb()
    why = ''
    idle = False
    if rss < _RSS_LIMIT_MB:
        over, inst, lim = _instance_over()
        if over:
            why = f' · 인스턴스 합계 {inst} ≥ 문지기 {lim}'
        else:
            idle, why = _idle_floor_due()
            if not idle:
                return
    # Z10-B(오너 2026-10-11): 잡·크론이 도는 중이면 갈아끼우지 않는다 — 그 잡을 죽이면 카드가 「검증 못 함」으로 끝나고
    #   다시 누르면 같은 일을 처음부터 한다. 잡이 끝난 뒤 첫 요청에서 다시 본다.
    busy = _active_jobs()
    if busy:
        worker.log.warning('[RSS] worker pid=%s rss_mb=%d (상한 %d%s) — 잡 %s 진행 중이라 이번엔 남는다', worker.pid, rss, _RSS_LIMIT_MB, why, busy)
        return
    import time as _t
    try:
        last = os.path.getmtime(_RSS_STAMP)
    except OSError:
        last = 0
    if _t.time() - last < _RSS_GAP_SEC:
        worker.log.warning('[RSS] worker pid=%s rss_mb=%d (상한 %d%s) — 다른 워커가 방금 재시작해 이번엔 남는다', worker.pid, rss, _RSS_LIMIT_MB, why)
        return
    try:
        with open(_RSS_STAMP, 'w') as fh:
            fh.write(str(worker.pid))
    except OSError:
        pass
    if idle:
        try:
            with open(_IDLE_STAMP, 'w') as fh:
                fh.write(str(worker.pid))
        except OSError:
            pass
    worker.log.warning('[RSS] worker pid=%s rss_mb=%d (상한 %d%s) — 이 워커만 재시작(받던 요청은 끝내고)', worker.pid, rss, _RSS_LIMIT_MB, why)
    # 순찰 73: 사유·전후 MB를 운영 DB에(`rss:restart`) — 로그 없이도 「왜 바뀌었나」를 본다
    try:
        from src.utils import restart_log as _rl
        _rl.note_exit('쉬는 동안 바닥' if idle else ('인스턴스 합계' if why else '워커 RSS'), pid=worker.pid, worker_mb=rss,
                      inst_mb=_inst_seen['mb'], worker_limit=_RSS_LIMIT_MB, inst_limit=_inst_seen['lim'])
    except Exception:                                            # noqa: BLE001
        pass
    worker.alive = False
