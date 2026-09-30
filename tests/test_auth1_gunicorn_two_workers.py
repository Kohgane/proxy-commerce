"""AUTH-1 — **gunicorn 워커 2개**에서 가입 → 로그인 → 보호 페이지까지 튕김 0 (curl 시나리오).

인메모리 테스트는 한 프로세스라 「가입은 워커 A, 다음 요청은 워커 B」를 못 잰다.
운영과 같은 모양 — `gunicorn -c gunicorn.conf.py -w 2` + PG + **SECRET_KEY 없음**(최악) — 으로 띄워
curl `-c/-b`(쿠키 저장·재전송)로 잰다. 보호 페이지 요청은 매번 새 연결이라 두 워커에 흩어진다
(접근 로그의 pid로 **실제로 두 워커를 탔는지** 확인한다 — 한 워커만 탔으면 이 계약은 아무것도 안 잰 것이다).

PG가 있을 때만 돈다(CI pg-suite 레인 · 로컬 `DATABASE_URL`).
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    not (os.getenv("DATABASE_URL") and shutil.which("curl") and shutil.which("gunicorn")),
    reason="PG(DATABASE_URL)·curl·gunicorn이 있을 때만 — CI pg-suite 레인에서 돈다")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server():
    tmp = Path(tempfile.mkdtemp(prefix="auth1-"))
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "GOOGLE_SHEET_ID", "APP_ENV")}
    url = os.environ["DATABASE_URL"]
    env.update({"PORT": str(port), "SELLER_CONSOLE_AUTH": "1", "SUPABASE_DB_URL": url,
                "DATABASE_URL_DIRECT": os.getenv("DATABASE_URL_DIRECT", url),
                "SESSION_SECRET_FILE": str(tmp / "session_secret"), "PYTHONUNBUFFERED": "1",
                "KGP_SHORT_LINK_RESOLVE": "0"})
    log = open(tmp / "gunicorn.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "src.order_webhook:app", "-c", "gunicorn.conf.py", "-w", "2",
         "--threads", "2", "--bind", f"127.0.0.1:{port}", "--access-logfile", str(tmp / "access.log"),
         "--access-logformat", "%(p)s %(m)s %(U)s %(s)s"],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            if subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", base + "/health"],
                              capture_output=True, text=True, timeout=5).stdout == "200":
                break
        except Exception:
            pass
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    else:
        proc.terminate()
        pytest.fail("gunicorn이 뜨지 않았다:\n" + (tmp / "gunicorn.log").read_text()[-3000:])
    if proc.poll() is not None:
        pytest.fail("gunicorn이 죽었다:\n" + (tmp / "gunicorn.log").read_text()[-3000:])
    yield {"base": base, "tmp": tmp}
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        proc.kill()
    log.close()
    shutil.rmtree(tmp, ignore_errors=True)


def _curl(base, jar, method, path, data=None):
    """→ (status, location, set_cookie_seen, body). 매번 새 연결(워커가 흩어지게)."""
    hfile, bfile = Path(str(jar) + ".h"), Path(str(jar) + ".b")
    args = ["curl", "-s", "-c", str(jar), "-b", str(jar), "-H", "Connection: close", "-X", method,
            "-D", str(hfile), "-o", str(bfile), base + path]
    for k, v in (data or {}).items():
        args += ["--data-urlencode", f"{k}={v}"]
    subprocess.run(args, capture_output=True, timeout=30)
    head = hfile.read_text(encoding="utf-8", errors="replace")
    body = bfile.read_text(encoding="utf-8", errors="replace")
    status = int(head.split()[1]) if head.startswith("HTTP/") else 0
    loc = next((ln.split(":", 1)[1].strip() for ln in head.splitlines() if ln.lower().startswith("location:")), "")
    cookie = any(ln.lower().startswith("set-cookie: session=") for ln in head.splitlines())
    return status, loc, cookie, body


def test_signup_then_protected_pages_on_both_workers(server):
    base, tmp = server["base"], server["tmp"]
    jar = tmp / "jar.txt"
    email = f"auth1-{uuid.uuid4().hex[:8]}@example.test"

    st, loc, cookie, _ = _curl(base, jar, "POST", "/auth/signup",
                               {"email": email, "password": "pass12345", "name": "두워커"})
    assert st == 302 and loc.endswith("/seller/dashboard") and cookie, (st, loc, cookie)

    codes = [_curl(base, jar, "GET", "/seller/dashboard")[0] for _ in range(16)]
    assert codes == [200] * 16, codes                                     # 튕김 0

    pids = {ln.split()[0] for ln in (tmp / "access.log").read_text().splitlines()
            if " GET /seller/dashboard 200" in ln}
    assert len(pids) >= 2, f"한 워커만 탔다 — 계약이 두 워커를 재지 못했다: {pids}"

    _curl(base, jar, "GET", "/auth/logout")
    st, _, _, body = _curl(base, jar, "POST", "/auth/login", {"email": email, "password": "wrong-pass"})
    assert st == 401 and "비밀번호가 틀립니다" in body
    st, _, _, body = _curl(base, jar, "POST", "/auth/login", {"email": "nobody-" + email, "password": "x" * 9})
    assert st == 401 and "등록되지 않은 이메일" in body
    st, loc, cookie, _ = _curl(base, jar, "POST", "/auth/login", {"email": email, "password": "pass12345"})
    assert st == 302 and loc.endswith("/seller/dashboard") and cookie
    assert [_curl(base, jar, "GET", "/seller/dashboard")[0] for _ in range(6)] == [200] * 6
