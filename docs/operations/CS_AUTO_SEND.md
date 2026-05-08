# CS 자동 발송 운영 가이드 (Phase 139)

## 기본 정책
- 기본값은 `CS_AUTO_SEND=0` (OFF) 입니다.
- 보수적으로 `general,shipping` 카테고리만 자동 발송 허용합니다.

## 환경변수
- `CS_AUTO_SEND=0`
- `CS_AUTO_SEND_CATEGORIES=general,shipping`
- `CS_AUTO_SEND_CONFIDENCE_THRESHOLD=0.85`
- `CS_AUTO_SEND_DAILY_LIMIT=20`

## 차단 조건
- 카테고리 화이트리스트 미포함
- 신뢰도 임계값 미달
- 템플릿 변수 미치환(`{{...}}` 잔존)
- 일일 한도 초과

## 보안 권고
- 운영 초기에는 반드시 OFF 유지 후 샘플 검증
- 자동 발송 ON 시 텔레그램 사후 검토 알림 확인
- 환불/사이즈/재고 카테고리는 운영자 승인 유지 권장
