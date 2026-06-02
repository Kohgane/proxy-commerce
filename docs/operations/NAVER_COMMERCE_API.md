# NAVER_COMMERCE_API (Phase 151)

토큰 발급 헬퍼 위치: `src/markets/adapters/naver_commerce_auth.py`

## 환경변수

- `NAVER_COMMERCE_CLIENT_ID`
- `NAVER_COMMERCE_CLIENT_SECRET`
- `NAVER_COMMERCE_API_BASE` (기본 `https://api.commerce.naver.com/external`)

## 토큰 발급

- 엔드포인트: `/v1/oauth2/token`
- grant type: `client_credentials`
- type: `SELF`
- 요청 필드:
  - `client_id`
  - `timestamp` (ms)
- `client_secret_sign`
- `grant_type`
- `type`

`client_secret_sign` 생성 시 현재 helper는 bcrypt-formatted salt 형태의
`NAVER_COMMERCE_CLIENT_SECRET`를 기대합니다. 토큰은 메모리 캐시에 저장되며
만료 직전 자동 갱신됩니다.

---

# 🔴 HANDOFF / 메모 — 네이버 동기화 403 IP_NOT_ALLOWED (진행 중)

> 최종 업데이트: 2026-06-02 · 담당 컨텍스트: proxy-commerce 안정화 + 셀러 콘솔 UX

## 현재 상태 (TL;DR)
- 워크플로 `KOHGANE Naver Sync` (`.github/workflows/workflow_naver_sync.yml`
  → `automation/api_sync/naver_commerce_sync.py`) 가 **403 `GW.IP_NOT_ALLOWED`** 로 실패 중.
- bcrypt 서명/시크릿 문제는 **해결됨** (시크릿 갱신 후 400 → 403 으로 전진).
- 남은 단 하나의 벽: **호출 IP가 네이버 화이트리스트에 없음.**

## 제약 (확정된 사실 — 다시 묻지 말 것)
- 네이버 커머스 앱은 **스토어당 1개만** 생성 가능 → 새 앱 못 만듦.
- API 호출 허용 IP는 **최대 3개**, 현재 3칸 모두 사용 중:
  - `50.6.34.133`  → **Cluely(다른 시스템)가 사용 중. 절대 건드리지 말 것.**
  - `54.226.173.178` → **정체불명/미사용으로 판단됨 (owner가 "모름" 확인).
    → 이 칸을 교체 대상으로 사용 가능.** (AWS 대역)
  - `50.6.34.63`   → **Cluely(다른 시스템)가 사용 중. 절대 건드리지 말 것.**
- GitHub Actions 러너는 outbound IP가 매번 바뀌어 화이트리스트 불가.
- QuotaGuard/Fixie 같은 **월 구독 프록시는 사용 안 함** (owner 결정).

## 채택 해법 — Oracle Cloud Always Free 로 무료 고정 IP 프록시
1. Oracle Cloud "Always Free" VM (영구 무료, 전용 공인 IP) 생성.
2. VM 에 `tinyproxy` 설치 → HTTPS forward proxy 로 사용.
3. 그 VM 의 **고정 IP 를 네이버 IP 3칸 중 `54.226.173.178` 자리에 교체 등록**.
   (Cluely 의 `50.6.34.x` 두 개는 그대로 둠)
4. 그 프록시 URL 을 GitHub Secret `NAVER_HTTPS_PROXY` 에 저장.
5. Phase 158 코드가 네이버 호출만 이 프록시로 경유 → 통과.

## 코드 측 준비 상태
- **Phase 158 (PR 진행 중):** `naver_commerce_sync.py` 가 `NAVER_HTTPS_PROXY`
  (또는 `QUOTAGUARD_URL`, `HTTPS_PROXY`) 를 읽어 **네이버 호출에만** 프록시 적용.
  WooCommerce/텔레그램은 직접 호출 유지. 프록시 미설정 시 기존 동작 100% 보존.
  실행 시 현재 outbound IP 를 로그로 출력 + 403/시크릿/429 진단 강화.
- 즉 **운영자는 프록시 URL 만 Secret 에 넣으면 즉시 작동.**

## 운영자(Owner) To-Do 체크리스트
- [ ] Oracle Cloud Always Free 가입 + VM 생성 (리전: 가능하면 Singapore/Seoul 인접)
- [ ] tinyproxy 설치 + 인증 설정 (아래 SETUP 참조)
- [ ] Oracle 보안목록/방화벽에서 프록시 포트(예: 8888) 인바운드 허용
- [ ] 네이버 커머스API센터 → 내 스토어 애플리케이션 → API호출 IP:
      `54.226.173.178` 삭제 → Oracle VM 공인 IP 추가 → 저장
- [ ] GitHub repo → Settings → Secrets → Actions:
      `NAVER_HTTPS_PROXY = http://<user>:<pass>@<ORACLE_IP>:8888`
- [ ] `KOHGANE Naver Sync` 워크플로 수동 실행(Run workflow) → 토큰 발급 통과 확인
- [ ] (선택) 추후 GitHub Actions → Render Cron 으로 이전

## tinyproxy SETUP (Oracle Ubuntu VM 기준)
```bash
# 1) 설치
sudo apt update && sudo apt install -y tinyproxy

# 2) 설정 편집
sudo nano /etc/tinyproxy/tinyproxy.conf
#   Port 8888
#   (Allow 라인들을 주석 처리하거나 GitHub/Render IP 만 허용)
#   BasicAuth naveruser <강력한_비밀번호>   ← 인증 추가 권장

# 3) 재시작
sudo systemctl restart tinyproxy
sudo systemctl enable tinyproxy

# 4) Oracle 보안: 인바운드 8888 허용
#    - VM 인스턴스 → Subnet → Security List → Ingress Rule 추가 (TCP 8888)
#    - sudo iptables -I INPUT -p tcp --dport 8888 -j ACCEPT (필요 시)

# 5) 검증 (로컬에서)
curl -x http://naveruser:<비밀번호>@<ORACLE_IP>:8888 https://api.ipify.org
#   → <ORACLE_IP> 가 출력되면 성공. 이 IP 를 네이버에 등록.
```

## 보안 주의
- tinyproxy 는 반드시 **BasicAuth** 또는 **출발지 IP 제한** 을 걸 것 (오픈 프록시 금지).
- 프록시 URL(`user:pass`) 은 로그/커밋에 평문 노출 금지. GitHub Secret 으로만 관리.

## 관련 파일
- 워크플로: `.github/workflows/workflow_naver_sync.yml`
- 스크립트: `automation/api_sync/naver_commerce_sync.py`
- 정식 헬퍼(중복 구현, 통합 후보): `src/markets/adapters/naver_commerce_auth.py`
