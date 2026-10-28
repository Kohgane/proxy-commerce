"""순찰 139(감독 2026-10-28 01:15 · 오너 결정 10-22) — 도검은 차단이 아니라 서류로 통과하는 보류 · 건기식·화장품은 서류 기반.

- `cert:knife` 보류(`docs=[knife_license]` · 총포화약법 제6조). 서류 있으면 주의(통과) · 없으면 보류 + 「서류 추가하면 자동 통과」.
  주방 식칼·과도·가위·커터칼은 도검이 아니다 — 오탐 0.
- 건기식·화장품: 「인허가 보유 — 주의」는 오너 계정(정본 오너 · `ADMIN_USER_IDS` · `FAMILY_EMAILS` · 잡 주인 없는 서버)만.
  다른 셀러는 `mfds_food`·`cosmetic` 서류 있을 때만 통과 · 없으면 보류 + 안내. 셀러 모름 = 보류(닫는다).
"""
import pytest


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    from src.db import image_translate_queue_pg as st
    from src.seller_console import market_credentials as mc
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    monkeypatch.setenv("ADMIN_USER_IDS", "u-family")
    monkeypatch.setenv("FAMILY_EMAILS", "")
    mc._shared_cache.clear()
    yield
    mc._shared_cache.clear()


def _hit(sc, key):
    return next((h for h in sc["hits"] if h["key"] == key), None)


@pytest.mark.parametrize("title", ["일본도 장식용 진검 100cm", "사시미칼 270mm 회칼", "匕首 战术刀 户外", "택티컬 나이프 서바이벌"])
def test_knife_is_held_and_passes_with_the_sellers_license(title):
    from src.services import risk_gate as R
    from src.seller_console import user_docs as UD
    h = _hit(R.scan({"title_ko": title}, owner={"u-other"}), "cert:knife")
    assert h["grade"] == "hold" and "총포·도검·화약류" in h["why"] and h["doc_hint"]["link"] == R.DOC_LINK
    assert "자동 통과" in h["why"] and "도검 판매업 허가" in h["doc_hint"]["need"]
    d = UD.add_doc("u-other", kind="knife_license", number="서울-도검-0001", valid_until="2099-12-31")
    h = _hit(R.scan({"title_ko": title}, owner={"u-other"}), "cert:knife")
    assert h["grade"] == "caution" and h["passed_by"]["doc_id"] == d["id"]


@pytest.mark.parametrize("title", ["주방 식칼 과도 세트 스테인리스", "剪刀 刀片 美工刀 文具", "菜刀 厨房刀具 不锈钢", "커터칼 칼날 리필",
                                   "버터 나이프 스푼 세트", "검정 원목 책상 점검용", "블랙 레더 지갑 검색 1위"])
def test_kitchen_knives_and_lookalike_words_are_not_knives(title):
    from src.services import risk_gate as R
    assert _hit(R.scan({"title_ko": title}, owner={"u-other"}), "cert:knife") is None


def test_knife_is_never_blocked_and_owner_account_also_needs_the_license():
    from src.services import risk_gate as R
    h = _hit(R.scan({"title_ko": "일본도 진검"}, owner={"default"}), "cert:knife")
    assert h["grade"] == "hold"                                                  # 「인허가 보유」 예외는 건기식·화장품만


@pytest.mark.parametrize("title,key,kind", [("건강기능식품 비타민 120정", "cert:supplement", "mfds_food"),
                                            ("화장품 세럼 30ml", "cert:cosmetic", "cosmetic")])
def test_supplement_and_cosmetic_for_other_sellers_need_documents(title, key, kind):
    from src.services import risk_gate as R
    from src.seller_console import user_docs as UD
    h = _hit(R.scan({"title_ko": title}, owner={"u-other", "other@test.local"}), key)
    assert h["grade"] == "hold" and h["doc_hint"]["link"] == R.DOC_LINK and "근거:" in h["why"]
    assert R.holds(R.scan({"title_ko": title}, owner={"u-other"}))                # 등록을 막는다
    assert _hit(R.scan({"title_ko": title}), key)["grade"] == "hold"              # 셀러 모름 = 보류
    d = UD.add_doc("u-other", kind=kind, number="제2026-0001호")
    h = _hit(R.scan({"title_ko": title}, owner={"u-other"}), key)
    assert h["grade"] == "caution" and h["passed_by"] == {"by": "user_doc", "doc_id": d["id"], "kind": kind, "number": "제2026-0001호"}


@pytest.mark.parametrize("owner", [{"f275b60d-9728-4349-9f44-00cedb037516"}, {"u-family"}, {"default"}])
def test_owner_accounts_keep_the_licensed_caution(owner, monkeypatch):
    from src.services import risk_gate as R
    monkeypatch.setattr("src.auth.identity.OWNER_USER_ID", "f275b60d-9728-4349-9f44-00cedb037516")
    for title, key, label in (("건강기능식품 비타민 120정", "cert:supplement", "건강기능식품(인허가 보유)"),
                              ("화장품 세럼 30ml", "cert:cosmetic", "화장품(인허가 보유)")):
        sc = R.scan({"title_ko": title}, owner=owner)
        h = _hit(sc, key)
        assert (h["grade"], h["label"], h["cat"], h["why"]) == ("caution", label, label, "인허가 보유 — 표시·광고 문구만 확인")
        assert h["passed_by"] == {"by": "licensed_owner"} and not R.holds(sc)


def test_allowlist_by_the_old_label_still_skips(monkeypatch):
    from src.services import risk_gate as R
    monkeypatch.setattr(R, "allowlist", lambda: {"화장품(인허가 보유)"})
    assert _hit(R.scan({"title_ko": "화장품 세럼"}, owner={"u-other"}), "cert:cosmetic") is None


def test_doc_kind_is_on_the_me_page_choices():
    from src.seller_console import user_docs as UD
    assert UD.KINDS["knife_license"].startswith("도검 판매업 허가")
