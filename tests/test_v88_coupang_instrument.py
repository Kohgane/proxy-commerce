"""v88 C1 — 쿠팡 등록 계측(스마트스토어 #676과 동형).

부검이 막힌 근원 둘:
  ① 실패 사유가 generic 문구("API request failed after retries")로 뭉개져 **무엇이 거부됐는지** 알 수 없었다.
  ② **보낸 페이로드가 어디에도 남지 않았다**(등록 대장에 payload 컬럼 없음·성공 시에만 record).
     → "유효하지 않은 구매 옵션 값 혹은 단위" 거부의 attributes 원문을 사후에 볼 방법이 0이었다.

여기 계약은 그 둘을 못박는다. 저장처는 기존 로그 관례(logger) — 대장 스키마는 건드리지 않는다.
"""
import json
import logging
import re
from pathlib import Path

import pytest

from src.market_relay import RelayError
from src.uploaders.base_uploader import BaseUploader
from src.uploaders.coupang_uploader import CoupangUploader
from src.uploaders.naver_uploader import NaverSmartStoreUploader

POST_PATH = '/v2/providers/seller_api/apis/api/v1/marketplace/seller-products'


def _code_only(path: str) -> str:
    """주석·독스트링을 뺀 **실행되는 줄**만. 근거를 문서에 인용했다고 계약이 깨지면 안 된다."""
    src = Path(path).read_text(encoding='utf-8')
    src = re.sub(r'""".*?"""', '', src, flags=re.S)
    return '\n'.join(l for l in src.splitlines() if not l.lstrip().startswith('#'))


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
    assert 'market_registrations' not in _code_only('src/uploaders/coupang_uploader.py')


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


# ── 처방 A+B — 단위 결합 · 허용값 게이트 (오너 P1~P5) ─────────────────────────
# 부검 결론: 스키마 파서가 `basicUnit`/`usableUnits`를 **버려서** 단위가 붙을 경로 자체가 없었다.
# 쿠팡 거부 문구 "유효하지 않은 구매 옵션 값 **혹은 단위**"의 '단위' 쪽이 여기서 닫힌다.

META_ATTRS = [
    {'attributeTypeName': '수량', 'required': 'MANDATORY', 'dataType': 'NUMBER',
     'inputType': 'INPUT', 'basicUnit': '개', 'usableUnits': ['개']},
    {'attributeTypeName': '색상', 'required': 'MANDATORY', 'dataType': 'STRING',
     'inputType': 'SELECT', 'basicUnit': '', 'usableUnits': []},
    {'attributeTypeName': '중량', 'required': '', 'dataType': 'NUMBER',
     'inputType': 'INPUT', 'basicUnit': 'g', 'usableUnits': ['g', 'kg']},
]


def _schema(monkeypatch, up):
    monkeypatch.setattr(up, 'get_category_meta', lambda code: {'attributes': META_ATTRS})
    return up.get_category_attribute_schema('63955')


def test_p1_meta_keeps_unit_fields(monkeypatch):
    """P1 — `basicUnit`/`usableUnits`/`inputType`을 **보존**한다(여태 버리던 3필드)."""
    sch = _schema(monkeypatch, _uploader())
    qty = next(e for e in sch if e['attributeTypeName'] == '수량')
    assert qty['basicUnit'] == '개' and qty['usableUnits'] == ['개'] and qty['inputType'] == 'INPUT'


def test_p1_meta_attributes_are_logged(monkeypatch, caplog):
    """P1 — 메타 attributes[] **원문**이 로그에 남는다(다음 카나리에서 메타 확보)."""
    up = _uploader()
    with caplog.at_level(logging.INFO):
        _schema(monkeypatch, up)
    line = next(r.getMessage() for r in caplog.records if '카테고리 메타' in r.getMessage())
    assert 'usableUnits' in line and 'basicUnit' in line and 'code=63955' in line


def test_p2_unit_is_attached_from_meta_only(monkeypatch):
    """★ P2 — `수량=1` → `1개`. 단위는 **메타 유래**이고 하드코딩이 아니다."""
    sch = _schema(monkeypatch, _uploader())
    out = CoupangUploader.attr_safe([{'attributeTypeName': '수량', 'attributeValueName': '1'}],
                                    'PopSockets 그립톡', sch)
    assert out[0]['attributeValueName'] == '1개'
    # 메타에 단위가 없으면 결합하지 않는다(발명 0).
    out = CoupangUploader.attr_safe([{'attributeTypeName': '색상', 'attributeValueName': '블랙'}],
                                    'x', sch)
    assert out[0]['attributeValueName'] == '블랙'
    # 이미 단위가 붙어 있으면 이중 결합하지 않는다.
    out = CoupangUploader.attr_safe([{'attributeTypeName': '수량', 'attributeValueName': '2개'}],
                                    'x', sch)
    assert out[0]['attributeValueName'] == '2개'


def test_p2_no_hardcoded_unit_strings():
    """단위 문자열이 코드에 박히지 않았다 — 전부 메타에서 온다."""
    body = _code_only('src/uploaders/coupang_uploader.py')
    assert 'basicUnit' in body
    for banned in ("'개'", '"개"', "'kg'", "'ml'"):
        assert banned not in body, banned


def test_p3_value_outside_allowed_units_is_blocked(monkeypatch, caplog):
    """P3 — 메타 허용 목록 밖 단위는 **전송 전 차단** + 사유. 목록이 없으면 통과."""
    sch = _schema(monkeypatch, _uploader())
    with caplog.at_level(logging.INFO):
        out = CoupangUploader.attr_safe(
            [{'attributeTypeName': '수량', 'attributeValueName': '1'},
             {'attributeTypeName': '중량', 'attributeValueName': '45ml'}], 'x', sch)
    names = [a['attributeTypeName'] for a in out]
    assert '수량' in names and '중량' not in names          # 허용 밖 → 빠진다
    line = next(r.getMessage() for r in caplog.records if '옵션 차단' in r.getMessage())
    assert '45ml' in line and 'g/kg' in line                # 조용한 누락 금지
    # 스키마를 안 주면(=허용 목록 없음) 그대로 통과 — 회귀 0.
    assert CoupangUploader.attr_safe(
        [{'attributeTypeName': '중량', 'attributeValueName': '45ml'}], 'x')[0][
        'attributeValueName'] == '45ml'


def test_p4_failed_registration_is_logged_every_time(monkeypatch, caplog):
    """★ P4 — 대장은 성공만 적는다. 그래서 실패는 **호출마다 1줄씩** 누적한다(3회면 3줄).

    같은 상품을 3회 클릭했을 때 "실패 3회가 어디에도 없다"가 이번 부검을 막았다.
    등록 대장 스키마는 건드리지 않는다 — payload 컬럼 결정은 계속 보류.
    """
    up = _uploader()
    _open_gates(up, monkeypatch)
    monkeypatch.setattr('src.uploaders.coupang_uploader.relay_request',
                        lambda *a, **k: _Resp(400, '{"message":"유효하지 않은 구매 옵션 값 혹은 단위 입니다."}'))
    with caplog.at_level(logging.INFO):
        for _ in range(3):
            up.upload_product(dict(PRODUCT))
    lines = [r.getMessage() for r in caplog.records if '등록실패대장' in r.getMessage()]
    assert len(lines) == 3, lines                          # 3회가 1로 뭉개지지 않는다
    assert 'sku=CANARY-C3' in lines[0] and 'at=' in lines[0] and 'kind=rejected' in lines[0]


def test_p4_held_gate_also_reaches_the_ledger(monkeypatch, caplog):
    """전송 전 보류(held)도 '등록 안 됨'이다 — 대장 누적에서 빠지지 않는다."""
    up = _uploader()
    _open_gates(up, monkeypatch)
    monkeypatch.setattr(up, '_missing_shipping_config', lambda: ['COUPANG_RETURN_ZIP_CODE'])
    with caplog.at_level(logging.INFO):
        up.upload_product(dict(PRODUCT))
    line = next(r.getMessage() for r in caplog.records if '등록실패대장' in r.getMessage())
    assert 'kind=held' in line


def test_p4_ledger_is_a_single_gate():
    """실패 return이 10곳이라 각 자리에 흩뿌리면 한 곳을 빠뜨린다 — 관문 하나로 묶었다."""
    src = Path('src/uploaders/coupang_uploader.py').read_text(encoding='utf-8')
    assert src.count('self._ledger_fail(') == 1
    assert 'def _upload_product_inner' in src


def test_p2_gate_and_payload_use_the_same_block(monkeypatch, caplog):
    """게이트가 본 attributes와 **보낸** attributes가 같다(두 번 만들면 갈릴 수 있다)."""
    up = _uploader()
    _open_gates(up, monkeypatch)
    monkeypatch.setattr(up, 'get_category_meta', lambda code: {'attributes': META_ATTRS})
    monkeypatch.setattr(up, 'get_category_attribute_schema',
                        lambda code: CoupangUploader.get_category_attribute_schema(up, code))
    monkeypatch.setattr('src.uploaders.coupang_uploader.relay_request',
                        lambda *a, **k: _Resp(400, '{"message":"거부"}'))
    with caplog.at_level(logging.INFO):
        up.upload_product({**PRODUCT,
                           'attributes': [{'attributeTypeName': '수량', 'attributeValueName': '1'}]})
    line = next(r.getMessage() for r in caplog.records if '전송블록' in r.getMessage())
    assert '"attributeValueName": "1개"' in line       # 결합된 값 그대로 전송
