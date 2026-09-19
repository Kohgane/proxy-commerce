#!/usr/bin/env bash
# =============================================================================
# setup_relay_vps.sh — 고정 IP 마켓 API 릴레이를 VPS에 세운다 (F36)
#
# 왜 이게 있나
#   2026-09-19 06:3x UTC 실측: Bluehost의 정적 파일은 0.4초에 오는데
#   `mkt.php`와 멀티샵 도메인은 **45초 동안 0바이트**였다. PHP만 전면 정지 —
#   우리 코드 결함이 아니고, 우리가 고칠 수 있는 구간도 아니다.
#   쿠팡·스마트스토어는 IP 화이트리스트라 **반드시 릴레이를 탄다.** 그 한 대가
#   멈추면 두 마켓의 등록이 통째로 멈춘다. 그래서 집을 옮긴다.
#
# 이 스크립트가 하는 것 / 안 하는 것
#   한다   nginx + php-fpm + certbot 설치, docroot 구성, mkt.php 배치,
#          vhost + TLS, 그리고 **자기 점검**(공인 IP · 즉답 여부).
#   안 한다 mkt.php 수정(한 바이트도), 비밀 값 생성·입력, 앱 코드 변경,
#          옛 릴레이(Bluehost) 정리 — 그건 검증 뒤 사람이 한다.
#
# 쓰는 법 (Ubuntu 24.04, root)
#   bash setup_relay_vps.sh relay.example.com [you@example.com]
#     1번 인자 = 릴레이 도메인 (A 레코드가 **이 서버를 가리킨 뒤** 실행)
#     2번 인자 = Let's Encrypt 알림 이메일 (생략 가능)
# =============================================================================
set -euo pipefail

DOMAIN="${1:-}"
LE_EMAIL="${2:-}"

APP_DIR="/var/www/relay"
DOC_ROOT="${APP_DIR}/public"
# mkt.php가 `dirname(__DIR__) . '/kgp_relay_secret'`을 읽는다 →
#   docroot의 **상위**여야 한다. 경로를 바꾸면 릴레이가 키를 못 찾는다.
SECRET_FILE="${APP_DIR}/kgp_relay_secret"
VHOST="/etc/nginx/sites-available/kgp-relay.conf"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }
die()  { printf '\n\033[31m실패: %s\033[0m\n' "$*" >&2; exit 1; }

[ -n "$DOMAIN" ] || die "도메인을 인자로 주세요.  예:  bash $0 relay.example.com you@example.com"
[ "$(id -u)" = "0" ] || die "root로 실행하세요 (sudo bash $0 $DOMAIN)"

say "1/7  패키지 설치"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx php-fpm php-curl certbot python3-certbot-nginx curl ca-certificates

PHP_SOCK="$(ls -1 /run/php/php*-fpm.sock 2>/dev/null | head -n1 || true)"
[ -n "$PHP_SOCK" ] || die "php-fpm 소켓을 못 찾았습니다 (/run/php/php*-fpm.sock). php-fpm이 떴는지 확인하세요."
note "php-fpm 소켓: ${PHP_SOCK}"

say "2/7  디렉터리"
mkdir -p "$DOC_ROOT"
chown -R www-data:www-data "$APP_DIR"
chmod 755 "$APP_DIR" "$DOC_ROOT"
note "docroot: ${DOC_ROOT}"

say "3/7  mkt.php 배치 (레포 원본 그대로 — 한 바이트도 고치지 않는다)"
cat > "${DOC_ROOT}/mkt.php" <<'KGP_MKT_PHP_EOF'
<?php
/**
 * mkt.php — 고정 IP 마켓 API 릴레이 (Bluehost)
 *
 * 프로토콜(우리 코드가 이미 의존하는 계약 — src/market_relay.py:33):
 *   요청  POST { url, method, headers, body_b64 } + 헤더 X-KGP-Relay-Key
 *   응답  200 { status, content_type, body_b64 }        ← 마켓 응답을 **무가공** 전달
 *         200 { error: "..." }                          ← 릴레이 계층 실패
 *
 * ★ 이 파일이 고치는 것(F'' 2026-09-05): **바디 없는 PUT의 Content-Length.**
 *   승인요청 `PUT .../approvals`는 보낼 바디가 없다. curl에 POSTFIELDS를 안 주면
 *   Content-Length를 아예 안 붙이고, 쿠팡 게이트웨이가 `411 Length Required`로 끊는다.
 *   → **바디가 비어 있어도 POSTFIELDS를 항상 세팅**한다(빈 문자열). curl이 CL: 0을 붙인다.
 *
 * 서명 불변: 쿠팡 CEA는 method+path+date만 서명한다. URL·헤더를 여기서 바꾸지 않는다.
 * 무상태: 자격증명을 저장하지도 로깅하지도 않는다.
 */

declare(strict_types=1);

// ── 설정 ────────────────────────────────────────────────────────────────────
/**
 * 키 로딩 — **파일이 먼저, env는 폴백.**
 *
 * ★ F''' 부검(2026-09-05): 대체본이 키를 `getenv()`로만 읽게 **발명**해서 릴레이가 죽었다.
 *   원본은 docroot 상위의 비밀 파일에서 읽고 있었다(8/6 구축분). **공유 호스팅 PHP는
 *   셸 `export`를 보지 못한다** — SSH에서 넣은 환경변수는 웹 요청 프로세스에 없다.
 *   프로토콜 계약만 지키고 **비밀 로딩은 계약 밖**이라 사각이 됐다.
 *
 * 경로는 하드코딩하지 않는다: `dirname(__DIR__)` = docroot 상위(홈).
 * 유저명이 레포에 남지 않고, 계정이 바뀌어도 따라간다.
 */
function kgp_relay_key(): string {
    $file = dirname(__DIR__) . '/kgp_relay_secret';
    if (is_readable($file)) {
        $v = trim((string) file_get_contents($file));   // 끝 개행이 섞이면 키가 통째로 어긋난다
        if ($v !== '') {
            return $v;
        }
    }
    return trim((string) (getenv('KGP_RELAY_KEY') ?: ''));   // 폴백(env를 보는 환경용)
}

$RELAY_KEY = kgp_relay_key();

// 허용 호스트 — 우리 코드(_API_RELAY_ALLOWED_HOSTS)와 같은 집합이어야 한다.
$ALLOWED_HOSTS = [
    'api-gateway.coupang.com',
    'api.commerce.naver.com',
];

$TIMEOUT_SEC = 30;

// ── 응답 헬퍼 ───────────────────────────────────────────────────────────────
header('Content-Type: application/json; charset=utf-8');

function fail(string $msg, int $code = 200): void {
    http_response_code($code);
    echo json_encode(['error' => $msg], JSON_UNESCAPED_UNICODE);
    exit;
}

// ── 인증 ────────────────────────────────────────────────────────────────────
if ($RELAY_KEY === '') {
    // 어디를 봤는지 말한다 — '미설정'만 뜨면 다음 사람이 또 env부터 뒤진다.
    fail('릴레이 키 미설정 — docroot 상위 kgp_relay_secret 파일 또는 KGP_RELAY_KEY 환경변수를 확인하세요.');
}
$given = $_SERVER['HTTP_X_KGP_RELAY_KEY'] ?? '';
if (!hash_equals($RELAY_KEY, (string) $given)) {
    fail('릴레이 키 불일치', 403);
}
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    fail('POST만 허용', 405);
}

// ── 봉투 파싱 ───────────────────────────────────────────────────────────────
$raw = file_get_contents('php://input');
$env = json_decode((string) $raw, true);
if (!is_array($env)) {
    fail('봉투가 JSON이 아닙니다');
}

$url     = (string) ($env['url'] ?? '');
$method  = strtoupper((string) ($env['method'] ?? 'GET'));
$headers = is_array($env['headers'] ?? null) ? $env['headers'] : [];
$bodyB64 = (string) ($env['body_b64'] ?? '');

if ($url === '') {
    fail('url 없음');
}
$host = parse_url($url, PHP_URL_HOST);
if (!in_array((string) $host, $ALLOWED_HOSTS, true)) {
    fail('허용되지 않은 호스트: ' . (string) $host);
}
if (!in_array($method, ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], true)) {
    fail('허용되지 않은 메서드: ' . $method);
}

// base64는 빈 문자열도 정상 입력이다(바디 없음) — 실패와 구분한다.
$body = $bodyB64 === '' ? '' : base64_decode($bodyB64, true);
if ($body === false) {
    fail('body_b64를 해석하지 못했습니다');
}

// ── 헤더 조립 ───────────────────────────────────────────────────────────────
// 호출부가 준 헤더를 **그대로** 넘긴다(서명 유효). 단 Content-Length는 여기서 다시 계산한다 —
// 호출부 값과 실제 바이트가 어긋나면 게이트웨이가 끊는다.
$curlHeaders = [];
foreach ($headers as $k => $v) {
    $name = (string) $k;
    if (strcasecmp($name, 'Content-Length') === 0) {
        continue;                       // 아래에서 실제 길이로 다시 넣는다
    }
    if (strcasecmp($name, 'Host') === 0 || strcasecmp($name, 'Expect') === 0) {
        continue;                       // curl이 정한다 / 100-continue 방지
    }
    $curlHeaders[] = $name . ': ' . (string) $v;
}
// ★ F'' 핵심: 바디가 비어도 길이를 **명시**한다. 이게 없으면 411.
$curlHeaders[] = 'Content-Length: ' . strlen($body);
$curlHeaders[] = 'Expect:';             // curl 기본 100-continue 억제(빈 헤더로 제거)

// ── 전송 ────────────────────────────────────────────────────────────────────
$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_CUSTOMREQUEST  => $method,
    // ★ 바디가 비어 있어도 **항상** 세팅한다. 조건부로 두면 curl이 CL을 안 붙인다.
    CURLOPT_POSTFIELDS     => $body,
    CURLOPT_HTTPHEADER     => $curlHeaders,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HEADER         => false,
    CURLOPT_FOLLOWLOCATION => false,
    CURLOPT_TIMEOUT        => $TIMEOUT_SEC,
    CURLOPT_CONNECTTIMEOUT => 10,
    CURLOPT_SSL_VERIFYPEER => true,
    CURLOPT_SSL_VERIFYHOST => 2,
]);

$respBody = curl_exec($ch);
if ($respBody === false) {
    $err = curl_error($ch);
    curl_close($ch);
    fail('마켓에 닿지 못했습니다: ' . $err);
}
$status = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
$ctype  = (string) curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
curl_close($ch);

// 마켓 응답은 **가공하지 않는다** — 오류 페이지(HTML)도 그대로 넘겨야 부검이 된다.
echo json_encode([
    'status'       => $status,
    'content_type' => $ctype,
    'body_b64'     => base64_encode((string) $respBody),
], JSON_UNESCAPED_UNICODE);
KGP_MKT_PHP_EOF
chown www-data:www-data "${DOC_ROOT}/mkt.php"
chmod 644 "${DOC_ROOT}/mkt.php"

say "4/7  비밀 파일 (빈 파일 + 600 — 값은 오너가 채운다)"
if [ -s "$SECRET_FILE" ]; then
  note "이미 값이 들어 있습니다 — 건드리지 않습니다."
else
  : > "$SECRET_FILE"
fi
chown www-data:www-data "$SECRET_FILE"
chmod 600 "$SECRET_FILE"
note "경로: ${SECRET_FILE}   (docroot 상위 — 웹으로는 열리지 않는다)"

say "5/7  nginx vhost"
cat > "$VHOST" <<NGINX_EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    root ${DOC_ROOT};

    access_log /var/log/nginx/kgp-relay.access.log;
    error_log  /var/log/nginx/kgp-relay.error.log;

    # 릴레이 봉투는 작다. 큰 바디를 받을 이유가 없다.
    client_max_body_size 4m;

    # 이 서버가 내보내는 것은 mkt.php 하나뿐이다.
    #   나머지를 404로 닫아 두면 비밀 파일이 엉뚱한 자리에 놓여도 새지 않는다.
    location = /mkt.php {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:${PHP_SOCK};
        # 마켓 호출은 최대 30초(mkt.php의 CURLOPT_TIMEOUT)다. 그보다 넉넉히 준다 —
        #   여기서 먼저 끊으면 마켓 응답을 받아 놓고 버리게 된다.
        fastcgi_read_timeout 60s;
    }

    location / { return 404; }
}
NGINX_EOF
ln -sf "$VHOST" /etc/nginx/sites-enabled/kgp-relay.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
note "vhost: ${VHOST}  (server_name ${DOMAIN})"

say "6/7  TLS (certbot)"
set +e
if [ -n "$LE_EMAIL" ]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$LE_EMAIL" --redirect
else
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect
fi
CERTBOT_RC=$?
set -e
if [ "$CERTBOT_RC" != "0" ]; then
  note "certbot 실패(코드 ${CERTBOT_RC}) — 대개 DNS A 레코드가 아직 이 서버를 안 가리킵니다."
  note "DNS를 맞춘 뒤 다시:  certbot --nginx -d ${DOMAIN} --redirect"
  note "그 전까지 아래 점검은 http로 합니다(릴레이는 https로만 씁니다)."
  SCHEME="http"
else
  SCHEME="https"
fi

say "7/7  자기 점검"
PUBLIC_IP="$(curl -s --max-time 10 https://api.ipify.org || true)"
[ -n "$PUBLIC_IP" ] || note "공인 IP를 못 읽었습니다(ipify 무응답) — 'curl -s https://api.ipify.org'를 직접 확인하세요."
note "공인 IP: ${PUBLIC_IP:-확인 실패}"

RELAY_URL="${SCHEME}://${DOMAIN}/mkt.php"
# POST 없이 GET — 바디를 안 보내고 **즉답인지**를 본다.
#   Bluehost가 죽었을 때의 모양은 「45초 · 0바이트」였다. 그 반대를 확인한다.
PROBE="$(curl -s -o /tmp/kgp_probe.out -w '%{http_code} %{time_total}' --max-time 20 "$RELAY_URL" || echo '000 0')"
CODE="${PROBE%% *}"; SECS="${PROBE##* }"
note "GET ${RELAY_URL}  →  HTTP ${CODE} · ${SECS}s"
note "본문: $(head -c 200 /tmp/kgp_probe.out 2>/dev/null || true)"
rm -f /tmp/kgp_probe.out

# ★ mkt.php는 **키를 먼저** 보고 메서드를 나중에 본다(파일 64~73줄). 그래서 맨 GET은
#   405가 아니다 — 비밀이 비면 200 「키 미설정」, 채워졌으면 403 「키 불일치」다.
#   셋 다 「PHP가 살아서 즉답한다」는 같은 사실을 말한다. 지어내지 않고 그대로 읽는다.
case "$CODE" in
  200) note "판정: PHP 실행됨 · mkt.php 응답함. 비밀 파일이 아직 비어 있습니다(지금 단계에선 정상)." ;;
  403) note "판정: PHP 실행됨 · 비밀이 채워져 있고 키 없는 요청을 막았습니다." ;;
  405) note "판정: PHP 실행됨 · POST가 아니라 거절했습니다." ;;
  000) note "판정: 응답이 오지 않았습니다 — 옮겨 온 그 증상입니다. nginx/php-fpm 상태를 보세요." ;;
  *)   note "판정: 예상 밖 응답코드입니다. 위 본문을 그대로 보고하세요." ;;
esac

# 비밀이 이미 채워져 있으면 **오너가 요청한 그 점검**을 정확히 한다: 키를 붙인 GET → 405.
if [ -s "$SECRET_FILE" ]; then
  KEY="$(tr -d '\n' < "$SECRET_FILE")"
  KPROBE="$(curl -s -o /dev/null -w '%{http_code} %{time_total}' --max-time 20 \
              -H "X-KGP-Relay-Key: ${KEY}" "$RELAY_URL" || echo '000 0')"
  note "키를 붙인 GET  →  HTTP ${KPROBE%% *} · ${KPROBE##* }s  (기대: 405 「POST만 허용」)"
  [ "${KPROBE%% *}" = "405" ] && note "판정: 405 즉답 — 릴레이가 정상입니다." \
                              || note "판정: 405가 아닙니다. 비밀 값이 앱쪽 MARKET_API_RELAY_KEY와 같은지 확인하세요."
else
  note "(비밀 파일이 비어 있어 405 점검은 건너뜁니다 — 값을 채운 뒤 이 스크립트를 다시 실행하면 잽니다.)"
fi

cat <<FINAL

─────────────────────────────────────────────────────────────────────────────
다음은 사람이 합니다. 순서를 지키세요 — **추가 → 검증 → 제거**.

1) 비밀 채우기
     printf '%s' '<앱의 MARKET_API_RELAY_KEY와 똑같은 값>' > ${SECRET_FILE}
     chown www-data:www-data ${SECRET_FILE} && chmod 600 ${SECRET_FILE}
     (끝 개행이 섞이면 키가 통째로 어긋납니다. printf를 쓰세요.)

2) 앱에서 이 릴레이를 가리키기 (Render)
     MARKET_API_RELAY_URL = https://${DOMAIN}/mkt.php

3) 마켓 허용 IP에 **추가**합니다. 옛 Bluehost IP는 아직 **지우지 마세요.**

  ★ 이 IP를 쿠팡 Wing과 네이버 커머스 허용 IP 목록에 등록하세요: ${PUBLIC_IP:-<위에서 확인한 공인 IP>}

4) 검증: 마켓 연동 화면에서 쿠팡 「불러오기」가 성공해야 합니다.
     성공하기 전까지 Bluehost IP를 목록에서 제거하지 마세요.
─────────────────────────────────────────────────────────────────────────────
FINAL
