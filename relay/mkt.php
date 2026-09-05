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
// 키는 파일에 박지 말고 환경/별도 include로. 없으면 거부한다(열린 릴레이 금지).
$RELAY_KEY = getenv('KGP_RELAY_KEY') ?: '';

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
    fail('릴레이 키 미설정 — 서버 환경변수 KGP_RELAY_KEY를 설정하세요.');
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
