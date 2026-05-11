# 배송 모니터링 (Phase 145)

- 모듈: `src/shipping/tracker.py` (`ShippingMonitor`)
- 화면: `/seller/shipping/tracking`
- 환경변수:
  - `SHIPPING_TRACKER_PROVIDER=mock` (`mock | sweet_tracker | kakao`)
  - `SHIPPING_DELAY_ALERT_HOURS=24`

기능:
- 배송 상태 동기화
- 지연 의심 감지(설정 시간 초과)
- 분실 의심 감지(5일 무변동)
- 진단 카드 `/admin/diagnostics` 연동
