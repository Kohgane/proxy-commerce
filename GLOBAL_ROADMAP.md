# Proxy Commerce Global Roadmap

## 글로벌 확장 단계 (Phase 180~187)

- **Phase 180 (이번 PR)**: 글로벌 기반 — 다통화 모델(price+currency + price_krw 하위호환), country/currency/locale/region 메타, 어댑터 인터페이스 확장, 글로벌 판매처 스텁(Amazon/eBay/Shopify/Shopee), 국가/통화 UI, 로드맵 문서화
- **Phase 181 (진행중)**: 현지화 파이프라인 — LocalizationService(DeepL/OpenAI 재사용, 캐시, 미설정 시 정직 미번역), 상품 `localized` 저장/폴백, 셀러 콘솔 현지화 액션·locale 선택·번역본 미리보기/수정
- **Phase 182**: Shopify 실연동 파일럿(end-to-end 등록)
- **Phase 183**: eBay 어댑터 실연동
- **Phase 184**: Amazon SP-API 실연동(US/EU/JP)
- **Phase 185**: Shopee/Lazada 동남아 확장
- **Phase 186**: 글로벌 주문·배송·통관 통합
- **Phase 187**: 다통화 결제·정산 + 세금/관세

## 새 나라/새 마켓 추가 가이드

1. `src/markets/adapters/`에 새 어댑터 파일을 추가하고 `MarketAdapter`를 상속합니다.
2. 어댑터 클래스에 `market`, `country`, `currency`, `locale`, `region` 메타를 선언합니다.
3. `is_configured()`에 필요한 env 키 검증을 추가합니다.
4. `validate_listing()`/`upload_product()`는 실연동 전에는 반드시 **정직하게 stub/미연동 상태**를 반환합니다.
5. `src/markets/adapters/base.py`의 `MARKETPLACE_META`에 마켓 메타를 등록합니다.
6. `src/utils/env_catalog.py`의 `API_REGISTRY`에 해당 마켓 자격증명 키를 `ApiCategory.MARKETPLACE`로 등록합니다.
