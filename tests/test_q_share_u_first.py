"""Q(오너 2026-10-01) — 공유 시트 길 복구(링크를 맨 앞 `u=`에) + 번역 품질 2건.

## 실측(운영 도착 기록, 읽기 전용)
| UTC | 길 | 쿼리 | 키 | text | 디코드 | 결과 |
|---|---|---|---|---|---|---|
| 13:49:12 | 카드(复制链接 → 단축어) | 1893자 | clip,text,v | 123 | +1 | 담음 |
| 13:49:50 | 공유 시트(分享 → 고가브릿지수집) | **9자** | **text,v** | 0 | 0 | 빈 값 |
→ 공유 시트 길은 P 이전과 같은 자리(`text=` 직후)에서 잘렸다. clip 키조차 없다. 링크를 `u=`로 **맨 앞**에 싣는다.

## 계약
  1 u만 · text만 · 둘 다 · 둘 다 빔 · text 절단(`u=…&text=` 뒤가 9자처럼 비어 옴) 매트릭스 — u가 있으면 담긴다
  2 도착 기록에 링크 칸 길이(`u_len`)
  3 번역 제목 끝 문장 꼬리 제거(「…스탠드에 적합합니다」→「…스탠드」) · magsafe → 맥세이프
  4 쿠팡명(F53): 첫 구절에 유형 명사가 없으면 뒤에서 **그 구간의 머리 명사**를 붙인다(「…스마트폰 거치대」 — 시계가 아니라)
     첫 구절에 이미 있으면 그대로(수행방패 회귀 0)
"""
from __future__ import annotations

import re
from urllib.parse import quote

import pytest

ORIG = ("【淘宝】7天无理由退货 https://e.tb.cn/h.8DPCNppWAZAWzUT?tk=AwnsTobAumn HU926「创意Magsafe磁吸手机支架"
        "无线充电器底座手机磁吸充电桌面支架」\n点击链接直接打开 或者 淘宝搜索直接打开")
LINK = "https://e.tb.cn/h.8DPCNppWAZAWzUT?tk=AwnsTobAumn"


def enc1(s):
    return quote(s, safe=":/")


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_translate_queue_pg as st
    from src.collectors import ko_polish as kp
    st.reset_for_tests()
    kp.reset_cache()
    yield
    kp.reset_cache()


@pytest.fixture(autouse=True)
def _resolve(monkeypatch):
    """운영에선 Render가 e.tb.cn을 펴서 상품 번호를 얻는다(09-29~30 share 6건 실측). 이 환경은 e.tb.cn이 막혀 있어
    펴기를 대신한다 — 링크만 온 경우(u만·text 절단)는 **펴기로** 상품을 특정하기 때문."""
    import src.collectors.link_diag as LD
    monkeypatch.setattr(LD, "resolve_short_link", lambda url, **kw: {
        "ok": True, "item_id": "809968335363", "price": "39.90", "currency": "CNY", "reason": "ok",
        "canonical_url": "https://item.taobao.com/item.htm?id=809968335363", "final_status": 200, "elapsed_ms": 1})
    monkeypatch.setenv("KGP_SHORT_LINK_RESOLVE", "1")


@pytest.fixture
def client():
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-q"
    return c


def _state(h):
    m = re.search(r'data-role="share-state"[^>]*>([^<]*)<', h)
    return m.group(1) if m else ""


@pytest.mark.parametrize("label,q,ok", [
    ("u만", f"v=2&u={enc1(LINK)}", True),
    ("text만", f"v=2&text={enc1(enc1(ORIG))}", True),
    ("둘 다", f"v=2&u={enc1(LINK)}&text={enc1(enc1(ORIG))}", True),
    ("둘 다 빔", "v=2&u=&text=", False),
    ("text 절단", f"v=2&u={enc1(LINK)}&text=", True),          # 공유 시트 길 실측: text= 뒤가 비어 옴
])
def test_u_text_matrix(client, label, q, ok):
    from src.seller_console.help_settings import share_arrivals
    h = client.get(f"/seller/collect/share?{q}").get_data(as_text=True)
    st = _state(h)
    if ok:
        assert st in ("담았어요", "이미 담은 상품이에요"), (label, st)
        assert "e.tb.cn" in re.sub(r"\s+", " ", h[h.index('data-stage="link"'):][:300])
    else:
        assert st == "담지 못했어요" and "단축어가 보낸 글이 비어 있어요" in h
    a = share_arrivals()[0]
    assert a["u_len"] == (len(LINK) if "u=h" in q else 0)


def test_u_wins_and_text_still_gives_title(client, monkeypatch):
    import json as _j
    import src.collectors.link_diag as LD
    from src.seller_console import collect_history_store as S
    seen = []
    monkeypatch.setattr(LD, "resolve_short_link", lambda url, **kw: seen.append(url) or {
        "ok": False, "item_id": "", "price": "", "currency": "", "reason": "no_item_in_body",
        "canonical_url": "", "final_status": 200, "elapsed_ms": 1})
    other = "https://e.tb.cn/h.OtherOther?tk=X"
    raw = f"【淘宝】{other} 「实木书桌」"
    h = client.get(f"/seller/collect/share?v=2&u={enc1(LINK)}&text={enc1(enc1(raw))}").get_data(as_text=True)
    assert _state(h) == "담았어요"
    assert seen and "h.8DPCNppWAZAWzUT" in seen[0]                             # 펴는 링크는 u가 1순위
    row = S.list_items(seller_ids={"u-q"}, days=1, limit=5)[0]
    ex = _j.loads(row["extra_json"])
    assert "实木书桌" in (ex.get("title") or "")                                 # 제목 재료는 text(「」)


def test_u_only_with_failed_resolution_fails_honestly(client, monkeypatch):
    import src.collectors.link_diag as LD
    monkeypatch.setattr(LD, "resolve_short_link", lambda url, **kw: {
        "ok": False, "item_id": "", "price": "", "currency": "", "reason": "timeout",
        "canonical_url": "", "final_status": 0, "elapsed_ms": 6000})
    h = client.get(f"/seller/collect/share?v=2&u={enc1(LINK)}&text=").get_data(as_text=True)
    assert _state(h) == "담지 못했어요"                                          # 제목도 상품 번호도 없으면 빈 행 0


def test_tail_and_magsafe_polish():
    from src.collectors import ko_polish as kp
    ko = "3-in-1 magsafe 자석 충전식 스마트폰·시계 무선 충전 거치대 및 이어폰 수납 데스크 스탠드에 적합합니다"
    out = kp.polish_ko(ko)
    assert out.endswith("데스크 스탠드") and "맥세이프" in out and "magsafe" not in out.lower()
    assert kp.polish_ko("충전 거치대 사용 가능합니다.") == "충전 거치대"
    assert kp.polish_ko("가방입니다") == "가방"
    assert kp.polish_ko("합니다") == "합니다"                                        # 다 떼면 빈 값 — 원래 값
    assert kp.polish_ko("임스 라운지 의자") == "임스 라운지 의자"                         # 명사로 끝나면 그대로


def test_coupang_name_keeps_the_product_type_noun():
    from src.collectors import ko_polish as kp
    from src.uploaders import coupang_title as ct
    ko = kp.polish_ko("3-in-1 magsafe 자석 충전식 스마트폰·시계 무선 충전 거치대 및 이어폰 수납 데스크 스탠드에 적합합니다")
    name = ct.build_name({"title_ko": ko, "options": [], "skus": []}, "front")["name"]
    assert name.endswith("거치대") and "시계" not in name, name                      # 충전 대상(시계)이 아니라 머리 명사
    # 첫 구절에 유형 명사가 있으면 그대로(F53 수행방패 회귀 0)
    sp = ct.build_name({"title_ko": "수행 방패(SPORTLINK)는 애플 워치 충전 거치대, 에어팟 겸용", "options": [], "skus": []},
                       "front")["name"]
    assert sp == "SPORTLINK 애플워치 충전 거치대 (에어팟 겸용)"
    # 제목 어디에도 유형 명사가 없으면 지어내지 않는다
    assert ct.product_type("자석 충전식 스마트폰") == "자석 충전식 스마트폰"


def test_shortcut_name_is_the_deployed_one_everywhere(client):
    """Q 추가(오너 실측 — iCloud 설치 페이지): 배포 단축어 이름은 「고가브릿지수집」. 화면 A·B·C·결과 화면 모두 그 이름."""
    from src.order_webhook import app
    admin = app.test_client()
    with admin.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    pages = [app.test_client().get("/seller/guide/iphone").get_data(as_text=True),
             app.test_client().get("/seller/guide/iphone/use").get_data(as_text=True),
             admin.get("/seller/guide/iphone/make").get_data(as_text=True),
             client.get("/seller/collect/share?v=2&text=&clip=").get_data(as_text=True)]
    for h in pages:
        assert "고가브릿지로 수집" not in h and "고가브릿지수집" in h
    a = pages[0]
    assert "「단축어 추가」를 누르세요.</p>" in a and "공유 시트에 표시됨" in a          # 오너 실측 라벨 — (캡처 참고) 뗌
