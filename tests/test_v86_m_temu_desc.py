"""tests/test_v86_m_temu_desc.py — v86-M: 테무 상세설명(goodsProperty) 수집.

오너 실기기(1.5.142, db177c4) 진단 파일 근거: extracted가 price 12730·images 8·options·reviews
(전부 tier1)로 정상인데 description=none·detail_specs 0. 근본 = 추출기 _fromJson 워커가 테무
goodsProperty(스펙 배열 [{key, values[]}])를 안 읽어 specs가 비고, specs→상세설명 사다리가 안 탔다.

수리: 워커에 goodsProperty→specs 케이스 추가 → 기존 specs→desc 사다리가 상세를 채운다.
오너 실스냅샷 재현: 상세설명이 스펙 37개 클린 추출(전원 모드: USB 충전 …). 실페이지 하네스
(tests/test_v70_realpage_harness.py)의 temu-goodsproperty 픽스처가 behavioral 게이트다.

추출 변경이므로 실페이지 하네스 통과 필수(CLAUDE.md v70 STEP5) — 통과 확인 후 머지.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
FIX = Path("fixtures/realpages")


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.143"


def test_goodsproperty_spec_case_in_walker():
    # _fromJson 워커에 goodsProperty(유사) → res.specs 케이스가 있어야 한다.
    assert re.search(r"goodsproperty\|productproperty\|paramproperty\|attributelist", EX), \
        "goodsProperty 스펙 케이스 regex 없음"
    # 스펙을 res.specs로 밀어넣는다([{key, values[]}] → {k, v}).
    seg = EX.split("goodsproperty|productproperty", 1)[1][:1200]
    assert "res.specs.push" in seg, "goodsProperty를 specs로 안 넣음"
    assert (".key" in seg or "propertyName" in seg) and ".values" in seg, "key/values 파싱 누락"


def test_cleanspecs_dedupes_by_key():
    # goodsProperty가 캡처 JSON·인라인 등 여러 후보 상태에 중복 존재 → 스펙 중복 → 상세설명 이중 표기.
    # _cleanSpecs가 키(소문자) 기준으로 중복을 걷어내야 한다(오너 실스냅샷서 상세 366자 1벌, 이중 아님).
    m = re.search(r"function _cleanSpecs\(specs\)\s*\{([\s\S]*?)\n  \}", EX)
    assert m, "_cleanSpecs 정의 없음"
    body = m.group(1)
    assert "seen" in body and "toLowerCase()" in body and "if (seen[" in body, \
        "_cleanSpecs 키 기준 중복 제거 없음(상세 이중 표기 회귀 위험)"


def test_realpage_fixture_present_and_asserts_description():
    # behavioral 게이트(실페이지 하네스)가 물릴 테무 스펙 픽스처 + 상세설명 계약.
    html = FIX / "temu-goodsproperty.html"
    spec = FIX / "temu-goodsproperty.expected.json"
    assert html.exists() and spec.exists(), "temu-goodsproperty 픽스처 없음"
    s = json.loads(spec.read_text(encoding="utf-8"))
    assert s.get("description_contains") == "전원 모드", "상세설명 계약(스펙표) 누락"
    assert s.get("price") == "12730" and s.get("currency") == "KRW"
    # goodsProperty 구조가 픽스처에 실제로 들어 있어야 한다(회귀 시 즉시 빨감).
    h = html.read_text(encoding="utf-8")
    assert "goodsProperty" in h and "전원 모드" in h and "USB 충전" in h
