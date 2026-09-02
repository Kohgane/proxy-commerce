"""tests/test_k_intro_deck.py — K1a 소개서(신청 제출물)의 **사실성·단일 소스** 계약.

이 산출물은 외부(카카오·ESM)로 나간다. 그래서 여기 계약은 디자인이 아니라 **내용**을 지킨다:
없는 수치를 만들지 않았는가 · 금지 명의가 섞이지 않았는가 · pptx와 PDF가 같은 문구인가.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CONTENT = Path("docs/apply/intro_content.json")
PDF = Path("docs/apply/gogabridj_intro_kakao_v2.pdf")
PPTX = Path("docs/apply/gogabridj_intro_kakao_v2.pptx")


@pytest.fixture(scope="module")
def content():
    return json.loads(CONTENT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def deck_text():
    """pptx 텍스트 — **표준 라이브러리로만** 읽는다.

    `python-pptx`는 이 프로젝트 런타임 의존성이 아니다(소개서 생성은 개발 도구다).
    계약이 CI에서 조용히 스킵되면 지키는 게 없으므로, zip+정규식으로 직접 읽는다.
    """
    import re as _re
    import zipfile
    out = []
    with zipfile.ZipFile(PPTX) as z:
        for name in sorted(n for n in z.namelist()
                           if n.startswith("ppt/slides/slide") and n.endswith(".xml")):
            xml = z.read(name).decode("utf-8", "ignore")
            out.extend(_re.findall(r"<a:t>(.*?)</a:t>", xml, _re.S))
    return " | ".join(out)


def test_both_outputs_exist_and_fit_size():
    """PDF(제출용)와 pptx(편집용) 둘 다 · 10MB 이내."""
    for f in (PDF, PPTX):
        assert f.exists(), f
        assert f.stat().st_size < 10 * 1024 * 1024, (f, f.stat().st_size)


def test_single_content_source(content, deck_text):
    """★ 문구는 JSON **한 곳**에서 온다 — pptx와 PDF가 갈리지 않는다."""
    for gen in (Path("scripts/_build_intro_deck.js"), Path("scripts/build_intro_deck.py")):
        src = gen.read_text(encoding="utf-8")
        assert "intro_content.json" in src, gen
    # JSON의 핵심 문구가 실제로 pptx에 들어가 있다.
    assert content["sellers"]["headline"] in deck_text
    assert content["cover"]["tagline"] in deck_text


def _print_source() -> str:
    """PDF의 **인쇄 원본 HTML**. 이걸 검사하는 이유:

    Chromium이 만든 PDF는 서브셋 폰트 + 커스텀 인코딩이라 스트림에서 텍스트를 되뽑으면
    글자가 깨진다(실측 — 한글이 전부 깨져 나온다). 깨진 문자열에 `in` 검사를 걸면
    **무엇도 확인하지 못하면서 통과**한다. 그래서 PDF 바이트 대신, 그 PDF를 만든
    바로 그 HTML을 같은 생성기로 만들어 검사한다 — 실제로 지키는 계약이 된다.
    """
    import importlib.util
    import json as _json
    spec = importlib.util.spec_from_file_location("bid", "scripts/build_intro_deck.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_html(_json.loads(CONTENT.read_text(encoding="utf-8")))


def test_no_owner_fill_placeholders_remain(content, deck_text):
    """★ v2 = 기입 확정본. **[오너 기입] 잔존 0** — 콘텐츠·pptx·PDF 인쇄원본 전부."""
    import json as _json
    assert content["meta"]["owner_fill"] == []
    assert "[오너 기입" not in _json.dumps(content, ensure_ascii=False)
    assert "[오너 기입" not in deck_text                      # pptx
    assert "오너 기입" not in _print_source()                 # PDF 인쇄 원본


def test_contact_values_land_in_both_outputs(content, deck_text):
    """확정 연락처가 pptx와 PDF **양쪽에** — 한쪽만 갱신되는 사고 방지."""
    import json as _json
    email, phone = "cigua7134@gmail.com", "010-4526-8127"
    src = _print_source()
    for value in (email, phone):
        assert value in _json.dumps(content, ensure_ascii=False), value
        assert value in deck_text, f"pptx: {value}"
        assert value in src, f"pdf: {value}"
    assert "계약 후 4주" in deck_text and "12개월 내 50명" in deck_text


def test_facts_only_no_invented_numbers(deck_text):
    """수치는 확정 사실만: 판매자 2 · 마켓 3 · 수집 소스 13."""
    for n, label in (("2", "운영 판매자"), ("3", "연동 마켓"), ("13", "수집 소스")):
        assert label in deck_text
    assert "쿠팡 · 스마트스토어 · WooCommerce 실증 완료, 파일럿 판매자 2명 운용 중" in deck_text


def test_applicant_identity_is_gogane_only(deck_text):
    """★ 신청 명의는 **고가네(개인사업자)** — alaz ltd·우주대행 명의 사용 0."""
    assert "고가네 (개인사업자)" in deck_text and "고우진" in deck_text
    for banned in ("alaz", "ALAZ", "Alaz"):
        assert banned not in deck_text, banned
    # 우주대행은 **테스트 판매자**로만 등장한다(신청 명의가 아니다).
    assert "테스트 판매자" in deck_text


def test_no_internal_jargon_leaks(deck_text):
    """카나리 회차·내부 용어는 외부 문서에 넣지 않는다."""
    for jargon in ("카나리", "정본", "P4", "v88", "held", "durable"):
        assert jargon not in deck_text, jargon


def test_security_claims_are_implemented(content):
    """★ 보안 문구는 **코드에 있는 것만** — 없는 기능을 적지 않는다."""
    claims = {t for t, _ in content["security"]["items"]}
    assert "판매자별 키 암호화 저장" in claims
    mc = Path("src/seller_console/market_credentials.py").read_text(encoding="utf-8")
    assert "Fernet" in mc                                   # 암호화 저장 실재
    relay = Path("src/market_relay.py").read_text(encoding="utf-8")
    assert "_IP_GATED_MARKETS" in relay                     # 고정 IP 릴레이 실재
    base = Path("src/uploaders/base_uploader.py").read_text(encoding="utf-8")
    assert "_fail_detail" in base                           # 실패 원문 로깅 실재


def test_screens_are_real_captures(content):
    """화면은 실제 캡처 파일을 쓴다(목업 아님)."""
    for key in ("overview", "sellers"):
        shot = Path(content[key]["shot"])
        assert shot.exists() and shot.stat().st_size > 10_000, shot
