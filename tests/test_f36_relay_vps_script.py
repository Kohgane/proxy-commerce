"""F36 계약 — 릴레이를 옮기는 스크립트 하나. 앱 코드 변경 0.

## 왜 옮기나 (F35 실측, 2026-09-19 06:3x UTC)

Bluehost의 **정적 파일은 0.4초**에 오는데 `mkt.php`와 멀티샵 도메인은
**45초 · 0바이트**였다. PHP만 전면 정지 — 우리 결함도 아니고 우리가 고칠 구간도 아니다.

쿠팡·스마트스토어는 IP 화이트리스트라 **반드시 릴레이를 탄다.** 그 한 대가 멈추면
두 마켓의 등록이 통째로 멈춘다. **릴레이는 단일 실패점이다.**

## 이 판의 산출물

VPS에 붙여 넣을 **셸 스크립트 하나**. 앱은 한 줄도 안 바뀐다
(바뀌는 것은 Render의 `MARKET_API_RELAY_URL` 값 하나 — 그건 코드가 아니다).

## 지키는 것

- **`mkt.php`를 손대지 않는다.** 스크립트에 박힌 사본이 레포 원본과 **바이트 동일**해야 한다.
- **허용 호스트 집합 그대로.** 릴레이 PHP와 `market_relay._API_RELAY_ALLOWED_HOSTS`가 같아야 한다.
- 비밀 파일은 **빈 파일 + 600**만. 값은 사람이 채운다.
- 끝 문장은 **「이 IP를 Wing·네이버에 등록하세요」** — IP를 사람이 복사한다.

## 405 점검에 대한 정직한 기록

오너 지시는 「GET → 405 즉답」이었다. 그런데 `mkt.php`는 **키를 먼저** 보고 메서드를
나중에 본다(64~73줄). 그래서 **맨 GET은 405가 안 된다** — 비밀이 비면 200,
채워졌으면 403이다. `mkt.php`는 손대지 않기로 했으므로, 스크립트는
셋을 **모두 해석**하고, 비밀이 채워진 재실행에서 **키를 붙인 GET으로 정확히 405**를 잰다.
"""
from __future__ import annotations

import re
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "relay/setup_relay_vps.sh"
PHP = ROOT / "relay/mkt.php"


@pytest.fixture(scope="module")
def src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _embedded_php(text: str) -> str:
    m = re.search(r"<<'KGP_MKT_PHP_EOF'\n(.*?)\nKGP_MKT_PHP_EOF\n", text, re.S)
    assert m, "스크립트에서 mkt.php 사본을 못 찾았다"
    return m.group(1) + "\n"


# ---------------------------------------------------------------------------
# ① mkt.php를 손대지 않는다
# ---------------------------------------------------------------------------

def test_the_embedded_php_is_byte_identical(src):
    """★★ **F36의 판정 지점** — 사본이 원본과 **바이트 동일**하다.

    사본이 있으면 언젠가 갈린다. 갈리는 순간을 사람이 못 보므로 계약이 본다
    (같은 병을 F34-2가 이미 한 번 보여 줬다).
    """
    assert _embedded_php(src) == PHP.read_text(encoding="utf-8")


def test_the_script_never_edits_the_php(src):
    """배치만 한다 — `sed -i`·패치로 고치는 줄이 없다."""
    for bad in ("sed -i", "patch ", "perl -pi", "php -r"):
        assert bad not in src, bad


def test_the_allowed_hosts_stay_the_same(src):
    """★ 허용 호스트 집합이 앱과 **같다** — 여기서 넓히면 릴레이가 열린 문이 된다."""
    from src.market_relay import _API_RELAY_ALLOWED_HOSTS
    php = _embedded_php(src)
    block = re.search(r"\$ALLOWED_HOSTS = \[(.*?)\];", php, re.S)
    assert block, "허용 호스트 목록을 못 찾았다"
    hosts = set(re.findall(r"'([^']+)'", block.group(1)))
    assert hosts == set(_API_RELAY_ALLOWED_HOSTS), (hosts, _API_RELAY_ALLOWED_HOSTS)


# ---------------------------------------------------------------------------
# ② 비밀은 사람이 채운다
# ---------------------------------------------------------------------------

def test_the_secret_file_is_created_empty_with_600(src):
    """★ 빈 파일 + 600. **값을 만들어 주지 않는다** — 지어낸 키는 키가 아니다."""
    assert 'SECRET_FILE="${APP_DIR}/kgp_relay_secret"' in src
    assert 'chmod 600 "$SECRET_FILE"' in src
    assert ': > "$SECRET_FILE"' in src
    for bad in ("openssl rand", "uuidgen", "head -c 32 /dev/urandom"):
        assert bad not in src, f"비밀을 스크립트가 만들고 있다: {bad}"


def test_an_existing_secret_is_not_wiped(src):
    """★ 재실행이 이미 채운 값을 **지우지 않는다** — 재실행은 점검 수단이기도 하다."""
    assert 'if [ -s "$SECRET_FILE" ]; then' in src
    assert "건드리지 않습니다" in src


def test_the_secret_sits_above_the_docroot(src):
    """`mkt.php`가 `dirname(__DIR__)`에서 읽는다 — docroot **상위**여야 웹으로 안 열린다."""
    assert 'DOC_ROOT="${APP_DIR}/public"' in src
    assert "dirname(__DIR__) . '/kgp_relay_secret'" in _embedded_php(src)
    assert "location / { return 404; }" in src, "docroot 밖 요청을 닫지 않는다"


# ---------------------------------------------------------------------------
# ③ 설치·vhost — 도메인은 인자다
# ---------------------------------------------------------------------------

def test_the_domain_comes_from_an_argument(src):
    """★ 도메인을 박지 않는다. 안 주면 **시작하지 않는다.**"""
    assert 'DOMAIN="${1:-}"' in src
    assert '[ -n "$DOMAIN" ] || die' in src
    assert "server_name ${DOMAIN};" in src


def test_it_installs_what_it_needs(src):
    for pkg in ("nginx", "php-fpm", "php-curl", "certbot", "python3-certbot-nginx"):
        assert pkg in src, pkg


def test_the_php_socket_is_discovered_not_guessed(src):
    """★ 소켓 경로를 찍지 않는다 — PHP 버전이 바뀌면 그 줄이 조용히 틀린다."""
    assert "ls -1 /run/php/php*-fpm.sock" in src
    assert "fastcgi_pass unix:${PHP_SOCK};" in src


def test_a_certbot_failure_does_not_abort_the_run(src):
    """DNS가 아직 안 붙었을 수 있다 — 거기서 죽으면 **공인 IP도 못 보고 끝난다.**"""
    assert "CERTBOT_RC" in src
    assert "DNS A 레코드" in src
    assert 'SCHEME="http"' in src, "TLS 실패 시 점검을 아예 안 하고 끝낸다"


# ---------------------------------------------------------------------------
# ④ 자기 점검 — 즉답인지를 잰다
# ---------------------------------------------------------------------------

def test_it_prints_the_public_ip(src):
    assert "curl -s --max-time 10 https://api.ipify.org" in src
    assert "공인 IP" in src


def test_the_probe_is_a_get_and_measures_time(src):
    """★ 옮겨 온 증상이 「45초 · 0바이트」였다 — **코드와 시간**을 같이 잰다."""
    assert "%{http_code} %{time_total}" in src
    assert "-X POST" not in src, "POST로 찔러 보면 즉답 여부가 아니라 실호출이 된다"


@pytest.mark.parametrize("code", ["200", "403", "405", "000"])
def test_every_probe_outcome_is_interpreted(src, code):
    """★ 맨 GET은 405가 아닐 수 있다 — **세 경우를 다 읽는다**(지어내지 않는다)."""
    assert re.search(rf"^\s*{code}\)", src, re.M), code


def test_the_405_check_runs_when_the_secret_is_filled(src):
    """오너가 요청한 그 점검 — 키를 붙인 GET은 **405**여야 한다."""
    assert "X-KGP-Relay-Key: ${KEY}" in src
    assert '"${KPROBE%% *}" = "405"' in src


def test_it_says_why_a_bare_get_is_not_405(src):
    """정직 — 왜 맨 GET이 405가 아닌지 스크립트가 말한다(다음 사람이 또 헤매지 않게)."""
    assert "키를 먼저" in src and "405가 아니다" in src


# ---------------------------------------------------------------------------
# ⑤ 끝 문장 — IP를 사람이 복사한다
# ---------------------------------------------------------------------------

def test_it_ends_by_telling_the_owner_to_register_the_ip(src):
    """★★ 오너 계약 — 마지막이 **「이 IP를 Wing·네이버에 등록하세요」**다."""
    tail = src[-1400:]
    assert "Wing" in tail and "네이버" in tail and "등록" in tail
    assert "${PUBLIC_IP:-" in tail, "IP를 문장에 싣지 않는다"


def test_the_order_is_add_verify_remove(src):
    """★ **추가 → 검증 → 제거.** 「불러오기」가 될 때까지 옛 IP를 지우지 않는다."""
    tail = src[-1400:]
    assert "지우지 마세요" in tail
    assert "불러오기" in tail
    assert tail.index("추가") < tail.index("불러오기")


def test_it_points_the_app_by_env_not_by_code(src):
    """★ **코드 변경 0** — 앱이 바뀌는 것은 env 값 하나뿐이다."""
    assert "MARKET_API_RELAY_URL" in src
    assert "git " not in src and "pip install" not in src


# ---------------------------------------------------------------------------
# ⑥ 스크립트로서 성립하는가
# ---------------------------------------------------------------------------

def test_it_parses_as_bash():
    """★ 오너가 붙여 넣는 물건이다 — 문법이 깨져 있으면 그 자리에서 끝난다."""
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_it_is_strict_and_executable(src):
    assert src.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in src
    assert stat.S_IMODE(SCRIPT.stat().st_mode) & stat.S_IXUSR, "실행 비트가 없다"


def test_it_refuses_to_run_as_a_normal_user(src):
    assert '[ "$(id -u)" = "0" ] || die' in src
