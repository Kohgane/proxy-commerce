"""v88 C1 — 쿠팡 등록 계측(스마트스토어 #676과 동형).

부검이 막힌 근원 둘:
  ① 실패 사유가 generic 문구("API request failed after retries")로 뭉개져 **무엇이 거부됐는지** 알 수 없었다.
  ② **보낸 페이로드가 어디에도 남지 않았다**(등록 대장에 payload 컬럼 없음·성공 시에만 record).
     → "유효하지 않은 구매 옵션 값 혹은 단위" 거부의 attributes 원문을 사후에 볼 방법이 0이었다.

여기 계약은 그 둘을 못박는다. 저장처는 기존 로그 관례(logger) — 대장 스키마는 건드리지 않는다.
"""
import json
import logging
from pathlib import Path

import pytest

from src.market_relay import RelayError
from src.uploaders.base_uploader import BaseUploader
from src.uploaders.coupang_uploader import CoupangUploader
from src.uploaders.naver_uploader import NaverSmartStoreUploader

POST_PATH = '/v2/providers/seller_api/apis/api/v1/marketplace/seller-products'


def _uploader():
    return CoupangUploader(access_key='AK', secret_key='SK', vendor_id='A0001', account='gogane')


def _open_gates(up, monkeypatch):
    """POST 앞의 게이트(배송·카테고리·고시·속성)를 통과시킨다 — 관심사는 전송 이후 계측."""
    monkeypatch.setattr(up, '_missing_shipping_config', lambda: [])
    monkeypatch.setattr(up, 'resolve_delivery_company_code', lambda: 'CJGLS')
    monkeypatch.setattr(up, 'predict_category', lambda name: '63955')
    monkeypatch.setattr(up, 'get_category_notice_schema', lambda code: None)
    monkeypatch.setattr(up, '_build_notices', lambda p, s: ([], None))
    monkeypatch.setattr(up, 'get_category_attribute_schema', lambda code:
                        [{'attributeTypeName': '사이즈', 'required': 'MANDATORY', 'dataType': 'STRING'}])


PRODUCT = {'sku': 'CANARY-C3', 'title': '테스트 상품', 'price': 19900, 'stock': 3,
           'images': ['https://x/a.jpg'], 'description_html': '<p>x</p>',
           'options': [{'name': '사이즈', 'value': 'FREE'}]}


class _Resp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text
        self.content = text.encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError('4xx/5xx는 raise_for_status 전에 반환돼야 한다')

    def json(self):
        return json.loads(self.text)


# ── ① generic 문구 소멸 ────────────────────────────────────────────────────────

def test_generic_failure_message_is_gone():
    """사유는 단계·시도·유형·상태·본문으로만 말한다(주석의 옛 문구는 근거라 실행줄만 본다)."""
    lines = [l for l in Path('src/uploaders/coupang_uploader.py').read_text(encoding='utf-8').splitlines()
             if not l.lstrip().startswith('#')]
    code = '\n'.join(lines)
    for gone in ('API request failed after retries', 'Authentication failed (401)', 'Server error ('):
        assert gone not in code, gone


def test_4xx_surfaces_coupang_body_without_retry(monkeypatch):
    """★ 부검 근원: 4xx가 **원문째** 올라오고, 되풀이해도 같은 답이므로 1회로 끝난다."""
    up = _uploader()
    calls = []
    body = '{"code":"ERROR","message":"유효하지 않은 구매 옵션 값 혹은 단위 입니다."}'
    monkeypatch.setattr('src.uploaders.coupang_uploader.relay_request',
                        lambda *a, **k: calls.append(1) or _Resp(400, body))
    err = up._api_request('POST', POST_PATH, data={})['error']
    assert len(calls) == 1
    for token in (f'stage=POST {POST_PATH}', 'attempt=1', 'http_status=400', '유효하지 않은 구매 옵션'):
        assert token in err, (token, err)


def test_relay_death_is_distinguishable_from_market_rejection(monkeypatch):
    """릴레이가 죽은 것 vs 쿠팡이 거부한 것 — `error_type`으로 갈린다(RelayError는 RequestException 상속)."""
    up = _uploader()
    monkeypatch.setattr('time.sleep', lambda s: None)
    monkeypatch.setattr('src.uploaders.coupang_uploader.relay_request',
                        lambda *a, **k: (_ for _ in ()).throw(RelayError('릴레이 오류: 릴레이가 HTTP 504')))
    err = up._api_request('POST', POST_PATH, data={})['error']
    assert 'error_type=RelayError' in err and '504' in err


@pytest.mark.parametrize('status', [401, 500])
def test_auth_and_server_errors_carry_body(monkeypatch, status):
    up = _uploader()
    monkeypatch.setattr('time.sleep', lambda s: None)
    monkeypatch.setattr('src.uploaders.coupang_uploader.relay_request',
                        lambda *a, **k: _Resp(status, '{"message":"쿠팡이 말한 사유"}'))
    err = up._api_request('POST', POST_PATH, data={})['error']
    assert f'http_status={status}' in err and '쿠팡이 말한 사유' in err


# ── ② 전송 블록이 남는다(실패는 물론 성공도) ───────────────────────────────────

def test_failure_logs_sent_attributes_block(monkeypatch, caplog):
    """실패 시 **전송한 attributes 원문**이 로그에 남는다 — 사후 부검의 유일한 근거."""
    up = _uploader()
    _open_gates(up, monkeypatch)
    monkeypatch.setattr('src.uploaders.coupang_uploader.relay_request',
                        lambda *a, **k: _Resp(400, '{"message":"유효하지 않은 구매 옵션 값 혹은 단위 입니다."}'))
    with caplog.at_level(logging.INFO):
        out = up.upload_product(PRODUCT)
    assert out['success'] is False
    line = next(r.getMessage() for r in caplog.records if '전송블록' in r.getMessage())
    assert 'outcome=fail' in line and 'sku=CANARY-C3' in line
    assert 'attributeTypeName' in line and '사이즈' in line and 'FREE' in line


def test_success_also_logs_attributes_block(monkeypatch, caplog):
    """성공분도 남긴다 — 다음 실패의 **대조 정본**(통과한 attributes가 어떤 모양이었나)."""
    up = _uploader()
    _open_gates(up, monkeypatch)
    monkeypatch.setattr('time.sleep', lambda s: None)
    monkeypatch.setattr(up, 'request_approval', lambda pid: {'success': True})
    monkeypatch.setattr('src.uploaders.coupang_uploader.relay_request',
                        lambda *a, **k: _Resp(200, '{"code":"SUCCESS","data":123456}'))
    with caplog.at_level(logging.INFO):
        out = up.upload_product(PRODUCT)
    assert out['success'] is True
    line = next(r.getMessage() for r in caplog.records if '전송블록' in r.getMessage())
    assert 'outcome=ok' in line and 'sellerProductId=123456' in line and 'attributeTypeName' in line


def test_attr_block_logging_never_kills_upload():
    """계측이 등록을 죽이지 않는다 — 직렬화 불가 값이 들어와도 라인은 나온다."""
    line = CoupangUploader._log_attr_block('S1', {'items': [{'itemName': 'x', 'attributes': {object()}}]},
                                           outcome='fail')
    assert '직렬화 실패' in line and 'outcome=fail' in line


def test_registry_schema_untouched():
    """대장(market_registrations) 스키마는 건드리지 않는다 — 저장처는 로그(오너 지시 C2)."""
    lines = [l for l in Path('src/uploaders/coupang_uploader.py').read_text(encoding='utf-8').splitlines()
             if not l.lstrip().startswith('#')]
    assert 'market_registrations' not in '\n'.join(lines)


# ── ③ 이중 구현 금지 — 실패 계측 조립은 BaseUploader 단일 소스 ─────────────────

def test_fail_detail_is_single_source():
    """같은 규칙을 두 곳에 두면 한쪽만 고쳐진다(이번 세션 4례). 조립기는 base에만 산다."""
    assert 'FAIL_BODY_LIMIT' in Path('src/uploaders/base_uploader.py').read_text(encoding='utf-8')
    for mod in ('coupang_uploader', 'naver_uploader'):
        src = Path(f'src/uploaders/{mod}.py').read_text(encoding='utf-8')
        assert 'def _fail_detail' not in src, mod
        assert 'def _resp_body' not in src, mod
    for cls in (CoupangUploader, NaverSmartStoreUploader):
        assert cls._fail_detail is BaseUploader._fail_detail          # staticmethod
        assert cls._resp_body.__func__ is BaseUploader._resp_body.__func__   # classmethod


def test_fail_detail_shape():
    got = BaseUploader._fail_detail('POST /x', 2, status=400, body='본문')
    assert got == 'stage=POST /x attempt=2 http_status=400 body=본문'
