#!/usr/bin/env bash
# scripts/deploy_domain.sh — 도메인 배포 전체 자동화 wrapper
#
# 사용법:
#   ./scripts/deploy_domain.sh kohganepercentiii.com
#
# 흐름:
#   1. 환경변수 CF_API_TOKEN, RENDER_API_TOKEN 존재 확인
#   2. 현재 Render 도메인 슬롯 확인 → 가득 차면 인터랙티브 제거 안내
#   3. apex + www 두 개 Render에 추가
#   4. 실제 onrender.com 호스트 자동 추출
#   5. Cloudflare DNS 자동 설정 (--target auto)
#   6. SSL 발급 polling (curl -I https://<domain>/health 200 대기, 최대 30분)
#   7. 최종 결과 요약 출력
#
# 필요 환경변수:
#   CF_API_TOKEN      — Cloudflare API 토큰 (Zone:DNS:Edit 권한)
#   RENDER_API_TOKEN  — Render API 토큰
#
# 기본 Render 서비스 ID (변경 시 아래 변수 수정):
SERVICE_ID="${RENDER_SERVICE_ID:-srv-d78d5rfkijhs73868f8g}"

set -euo pipefail

# ── 컬러 출력 ────────────────────────────────────────────────
GREEN="\033[92m"
YELLOW="\033[93m"
RED="\033[91m"
BLUE="\033[94m"
RESET="\033[0m"

ok()   { echo -e "${GREEN}✓${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET} $*"; }
err()  { echo -e "${RED}✗${RESET} $*" >&2; }
info() { echo -e "${BLUE}▶${RESET} $*"; }

# ── 인자 확인 ────────────────────────────────────────────────
if [[ $# -lt 1 ]]; then
    err "도메인을 인자로 전달해주세요."
    echo "  사용법: $0 <apex-domain>"
    echo "  예시:   $0 kohganepercentiii.com"
    exit 1
fi

APEX="$1"
WWW="www.${APEX}"

echo ""
echo "========================================================"
echo "  도메인 배포 자동화 — ${APEX}"
echo "========================================================"
echo ""

# ── STEP 1: 환경변수 확인 ────────────────────────────────────
info "STEP 1: 환경변수 확인"

MISSING_VARS=()
[[ -z "${CF_API_TOKEN:-}" ]]     && MISSING_VARS+=("CF_API_TOKEN")
[[ -z "${RENDER_API_TOKEN:-}" ]] && MISSING_VARS+=("RENDER_API_TOKEN")

if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
    err "다음 환경변수가 설정되지 않았습니다:"
    for v in "${MISSING_VARS[@]}"; do
        echo "    export ${v}=<your-token>"
    done
    echo ""
    echo "  발급 방법:"
    echo "    CF_API_TOKEN     → https://dash.cloudflare.com/profile/api-tokens"
    echo "    RENDER_API_TOKEN → https://dashboard.render.com/u/settings#api-keys"
    exit 1
fi
ok "환경변수 확인 완료"

# ── STEP 2: Render 도메인 슬롯 확인 ─────────────────────────
echo ""
info "STEP 2: Render 도메인 슬롯 확인"

python3 scripts/render_domain_attach.py \
    --service-id "${SERVICE_ID}" \
    --list-domains

# 슬롯 만석 여부 감지 (exit code 2)
SLOT_STATUS=0
python3 scripts/render_domain_attach.py \
    --service-id "${SERVICE_ID}" \
    --domains "${APEX}" "${WWW}" \
    --no-poll 2>&1 || SLOT_STATUS=$?

if [[ "${SLOT_STATUS}" -eq 2 ]]; then
    warn "Hobby Tier 슬롯이 가득 찼습니다."
    echo ""
    echo "  현재 등록된 도메인 목록을 확인하고 제거할 도메인을 선택하세요."
    echo "  예시:"
    echo "    python3 scripts/render_domain_attach.py --service-id ${SERVICE_ID} --remove-domain <old-domain>"
    echo ""
    read -rp "  제거할 도메인을 입력하세요 (건너뛰려면 Enter): " REMOVE_DOMAIN
    if [[ -n "${REMOVE_DOMAIN}" ]]; then
        python3 scripts/render_domain_attach.py \
            --service-id "${SERVICE_ID}" \
            --remove-domain "${REMOVE_DOMAIN}"
        ok "${REMOVE_DOMAIN} 제거 완료"
    else
        warn "도메인 제거를 건너뛰었습니다. 슬롯이 가득 찬 상태에서는 추가가 실패할 수 있습니다."
    fi
fi

# ── STEP 3: apex + www Render에 추가 ─────────────────────────
echo ""
info "STEP 3: ${APEX} + ${WWW} → Render에 추가"

python3 scripts/render_domain_attach.py \
    --service-id "${SERVICE_ID}" \
    --domains "${APEX}" "${WWW}" \
    --no-poll

# ── STEP 4: 실제 onrender.com 호스트 추출 ────────────────────
echo ""
info "STEP 4: onrender.com 호스트 자동 조회"

RENDER_HOST=$(python3 - <<'PYEOF'
import json, os, sys, urllib.request

service_id = os.environ.get("RENDER_SERVICE_ID", "srv-d78d5rfkijhs73868f8g")
token = os.environ.get("RENDER_API_TOKEN", "")
url = f"https://api.render.com/v1/services/{service_id}"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode())
    svc_url = (
        data.get("serviceDetails", {}).get("url")
        or data.get("service", {}).get("url")
        or data.get("url") or ""
    )
    host = svc_url.replace("https://", "").replace("http://", "").rstrip("/")
    print(host)
except Exception as e:
    print("", file=sys.stderr)
PYEOF
) || true

if [[ -z "${RENDER_HOST}" ]]; then
    err "onrender.com 호스트를 가져오지 못했습니다."
    echo "  Render 대시보드 → 서비스 → Settings 에서 직접 확인 후"
    echo "  아래 명령으로 수동 실행하세요:"
    echo "    python3 scripts/cloudflare_setup.py --apex ${APEX} --target <your-host>.onrender.com"
    exit 1
fi

ok "Cloudflare Target: ${RENDER_HOST}"

# ── STEP 5: Cloudflare DNS 자동 설정 ─────────────────────────
echo ""
info "STEP 5: Cloudflare DNS 설정 (--target auto)"

python3 scripts/cloudflare_setup.py \
    --apex "${APEX}" \
    --target auto \
    --service-id "${SERVICE_ID}"

# ── STEP 6: SSL 발급 polling ──────────────────────────────────
echo ""
info "STEP 6: SSL 발급 대기 (최대 30분, 30초 간격)"

MAX_WAIT=60   # 30분 / 30초 = 60회
INTERVAL=30
SSL_OK=0

for i in $(seq 1 "${MAX_WAIT}"); do
    HTTP_CODE=$(curl -o /dev/null -s -w "%{http_code}" \
        --max-time 15 \
        -L \
        "https://${APEX}/health" 2>/tmp/deploy_curl_err.txt || echo "000")

    if [[ -s /tmp/deploy_curl_err.txt ]]; then
        warn "curl 에러 (참고): $(cat /tmp/deploy_curl_err.txt)"
    fi

    if [[ "${HTTP_CODE}" == "200" ]]; then
        ok "SSL 발급 완료! https://${APEX}/health → HTTP ${HTTP_CODE}"
        SSL_OK=1
        break
    fi

    echo "  [${i}/${MAX_WAIT}] https://${APEX}/health → HTTP ${HTTP_CODE} — ${INTERVAL}s 후 재시도"
    sleep "${INTERVAL}"
done

# ── STEP 7: 최종 결과 요약 ──────────────────────────────────
echo ""
echo "========================================================"
echo "  배포 결과 요약"
echo "========================================================"
echo "  도메인:          ${APEX}"
echo "  www:             ${WWW}"
echo "  Render Target:   ${RENDER_HOST}"
echo "  서비스 ID:       ${SERVICE_ID}"

if [[ "${SSL_OK}" -eq 1 ]]; then
    echo ""
    ok "🎉 배포 완료! 사이트가 정상 운영 중입니다."
    echo ""
    echo "  확인 URL:"
    echo "    https://${APEX}/health"
    echo "    https://${WWW}/health"
    echo ""
    echo "  다음 단계:"
    echo "    python3 scripts/render_smoke.py https://${APEX}"
else
    echo ""
    warn "SSL 발급이 30분 내에 완료되지 않았습니다."
    echo ""
    echo "  가능한 원인:"
    echo "    - DNS 전파가 아직 완료되지 않음 (최대 24시간)"
    echo "    - CAA 레코드 충돌 → dig ${APEX} CAA 확인"
    echo "    - Cloudflare 프록시 ON 상태 → DNS only로 변경 후 재시도"
    echo ""
    echo "  나중에 확인:"
    echo "    curl -I https://${APEX}/health"
    echo "    python3 scripts/render_domain_attach.py --list-domains"
    exit 1
fi

echo "========================================================"
echo ""
