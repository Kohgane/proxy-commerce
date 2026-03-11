"""국가별 통관/세금/배송 설정 DB.

docs/PROGRESS.md의 Phase 6 시장조사 데이터를 코드화한 것.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class CountryConfig:
    """국가별 통관/세금/배송 설정."""

    code: str                          # ISO 3166-1 alpha-2
    name: str                          # 영문 국가명
    name_ko: str                       # 한글 국가명
    currency: str                      # ISO 4217 통화 코드
    vat_rate: Decimal                  # VAT/GST 표준세율 (소수, 예: 0.20 = 20%)
    duty_rate: Decimal                 # 기본 관세율 (소수)
    de_minimis: Decimal                # 면세 기준액 (현지 통화)
    de_minimis_currency: str           # 면세 기준 통화
    incoterms: str                     # 추천 Incoterms ('DDP' or 'DAP')
    tier: int                          # 공략 우선순위 Tier (1, 2, 3)
    ioss_eligible: bool = False        # EU IOSS 적용 가능 여부
    ioss_threshold: Optional[Decimal] = None  # IOSS 한도 (EUR)
    notes: str = ''                    # 특이사항 메모
    locale: str = ''                   # 기본 로케일 (번역용)
    vat_on_shipping: bool = True       # 배송비에도 VAT 부과 여부


COUNTRY_DB: dict[str, CountryConfig] = {
    'US': CountryConfig(
        code='US', name='United States', name_ko='미국',
        currency='USD', vat_rate=Decimal('0'), duty_rate=Decimal('0.05'),
        de_minimis=Decimal('800'), de_minimis_currency='USD',
        incoterms='DAP', tier=1,
        notes='$800 de minimis 사실상 종료 방향, 주(State) 판매세는 별도 처리 필요',
        locale='en_US', vat_on_shipping=False,
    ),
    'GB': CountryConfig(
        code='GB', name='United Kingdom', name_ko='영국',
        currency='GBP', vat_rate=Decimal('0.20'), duty_rate=Decimal('0.04'),
        de_minimis=Decimal('135'), de_minimis_currency='GBP',
        incoterms='DDP', tier=1,
        notes='£135 이하: 판매자가 결제 시 VAT 부과/신고, £135 초과: 수입 시점 VAT+관세',
        locale='en_GB',
    ),
    'JP': CountryConfig(
        code='JP', name='Japan', name_ko='일본',
        currency='JPY', vat_rate=Decimal('0.10'), duty_rate=Decimal('0.05'),
        de_minimis=Decimal('10000'), de_minimis_currency='JPY',
        incoterms='DAP', tier=2,
        notes='총 과세가격 10,000엔 이하 면세 (일부 예외), 화장품/식품 별도 규정',
        locale='ja_JP',
    ),
    'TH': CountryConfig(
        code='TH', name='Thailand', name_ko='태국',
        currency='THB', vat_rate=Decimal('0.07'), duty_rate=Decimal('0.10'),
        de_minimis=Decimal('0'), de_minimis_currency='THB',
        incoterms='DAP', tier=2,
        notes='2026-01-01부터 1바트부터 수입관세+VAT 7% (저가면세 종료)',
        locale='th_TH',
    ),
    'VN': CountryConfig(
        code='VN', name='Vietnam', name_ko='베트남',
        currency='VND', vat_rate=Decimal('0.10'), duty_rate=Decimal('0.10'),
        de_minimis=Decimal('0'), de_minimis_currency='VND',
        incoterms='DAP', tier=2,
        notes='2025-02-18부터 100만동 이하 VAT 면제 폐지',
        locale='vi_VN',
    ),
    'ID': CountryConfig(
        code='ID', name='Indonesia', name_ko='인도네시아',
        currency='IDR', vat_rate=Decimal('0.11'), duty_rate=Decimal('0.075'),
        de_minimis=Decimal('3'), de_minimis_currency='USD',
        incoterms='DAP', tier=2,
        notes='FOB≤$3: 관세 면제+VAT 11%, $3~$1500: 관세 7.5%+VAT 11%',
        locale='id_ID',
    ),
    'PH': CountryConfig(
        code='PH', name='Philippines', name_ko='필리핀',
        currency='PHP', vat_rate=Decimal('0.12'), duty_rate=Decimal('0.05'),
        de_minimis=Decimal('10000'), de_minimis_currency='PHP',
        incoterms='DAP', tier=2,
        notes='10,000페소 이하 de minimis 면세, 수입 VAT 12%',
        locale='en_PH',
    ),
    'AE': CountryConfig(
        code='AE', name='United Arab Emirates', name_ko='UAE',
        currency='AED', vat_rate=Decimal('0.05'), duty_rate=Decimal('0.05'),
        de_minimis=Decimal('0'), de_minimis_currency='AED',
        incoterms='DAP', tier=2,
        notes='관세 대부분 5% CIF 기준, VAT 5%',
        locale='en_AE',
    ),
    'SA': CountryConfig(
        code='SA', name='Saudi Arabia', name_ko='사우디',
        currency='SAR', vat_rate=Decimal('0.15'), duty_rate=Decimal('0.05'),
        de_minimis=Decimal('0'), de_minimis_currency='SAR',
        incoterms='DAP', tier=2,
        notes='GCC 체계 5%+ 품목별 상향, VAT 15%, 통관 전자화 강화 추세',
        locale='ar_SA',
    ),
    'SG': CountryConfig(
        code='SG', name='Singapore', name_ko='싱가포르',
        currency='SGD', vat_rate=Decimal('0.09'), duty_rate=Decimal('0'),
        de_minimis=Decimal('400'), de_minimis_currency='SGD',
        incoterms='DAP', tier=2,
        notes='GST 9%, S$400 이하 항공/우편 면제 있으나 OVR 구조도 도입',
        locale='en_SG',
    ),
    'MY': CountryConfig(
        code='MY', name='Malaysia', name_ko='말레이시아',
        currency='MYR', vat_rate=Decimal('0.10'), duty_rate=Decimal('0.05'),
        de_minimis=Decimal('500'), de_minimis_currency='MYR',
        incoterms='DAP', tier=2,
        notes='LVG RM500 이하 판매세 10% (2024-01-01부터), 저가라도 세금 있음',
        locale='ms_MY',
    ),
    'PL': CountryConfig(
        code='PL', name='Poland', name_ko='폴란드',
        currency='PLN', vat_rate=Decimal('0.23'), duty_rate=Decimal('0.04'),
        de_minimis=Decimal('0'), de_minimis_currency='EUR',
        incoterms='DDP', tier=3,
        ioss_eligible=True, ioss_threshold=Decimal('150'),
        notes='EU IOSS 적용, €150 이하 VAT 단순화, K-뷰티 신흥 급성장',
        locale='pl_PL',
    ),
    'CN': CountryConfig(
        code='CN', name='China', name_ko='중국',
        currency='CNY', vat_rate=Decimal('0.13'), duty_rate=Decimal('0.10'),
        de_minimis=Decimal('50'), de_minimis_currency='CNY',
        incoterms='DAP', tier=3,
        notes='개인우편물: 세액50위안이하 면세, CBEC: 1회5000위안/연26000위안, 자동화 난이도 높음',
        locale='zh_CN',
    ),
}

SUPPORTED_COUNTRIES = list(COUNTRY_DB.keys())


def get_country(code: str) -> CountryConfig:
    """ISO alpha-2 코드로 국가 설정 조회."""
    code = code.upper().strip()
    if code not in COUNTRY_DB:
        raise ValueError(f"지원하지 않는 국가: {code}. 지원: {', '.join(SUPPORTED_COUNTRIES)}")
    return COUNTRY_DB[code]
