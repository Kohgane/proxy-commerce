"""Y14(오너 2026-10-21 06:19 SPORTLINK 결정) — 호환 표기 상표는 지우지 않고 바꾼다 · 사진은 글자 고치기 · 상세 첫 줄 고정 · AI 초안 재검사.

블랙리스트 게이트는 「애플」만 잡았고 iwatch·Airpods·에어팟은 못 잡았다(10-20 사전검증). 「빼고 등록」은 낱말을 지우기만 해서
「애플워치 호환 충전 거치대」가 「워치 호환 충전 거치대」가 됐을 것이다. 오너: 「스마트워치」·「무선 이어폰」으로 바꾼다.
"""
import json

from src.services import risk_gate as R

_TITLE = "SPORTLINK(SPORTLINK)는 애플워치 호환 충전 거치대 7 9용, S8 무선 신형 Ultra2 시계 거치대, 에어팟 호환 이어폰 거치대"


def _ex():
    return {"title": "수행 방패(SPORTLINK)는 애플 워치 충전 거치대 applewatch7 9용", "title_ko": _TITLE,
            "keywords": ["SPORTLINK", "애플", "워치", "applewatch7", "iwatch", "Airpods", "거치대"],
            "tags": ["SPORTLINK", "applewatch7", "Airpods"],
            "images_ko": [{"idx": 0, "status": "done", "target_text": "스포츠링크 삼합일 애플 워치 충전 거치대", "source_text": "适用苹果手表"}]}


def _compat(sc, label):
    return next(h for h in sc["hits"] if h["key"] == "compat:" + label)


def test_replace_swallows_trailing_digits_and_merges_repeats():
    names = ["애플워치", "애플 워치", "Apple Watch", "AppleWatch", "applewatch", "iWatch", "iwatch"]
    assert R._replace("applewatch7 iwatch 시계", names, "스마트워치") == "스마트워치 시계"
    assert R._replace("애플워치 호환 충전 거치대", names, "스마트워치") == "스마트워치 호환 충전 거치대"
    assert R._replace("에어팟스 에어팟스 프로", ["에어팟스", "에어팟"], "무선 이어폰") == "무선 이어폰 프로"


def test_scan_finds_compat_names_the_blacklist_missed():
    sc = R.scan(_ex())
    w, a = _compat(sc, "애플워치 호환 표기"), _compat(sc, "에어팟 호환 표기")
    assert w["to"] == "스마트워치" and a["to"] == "무선 이어폰" and w["grade"] == "hold"
    assert {"applewatch", "iwatch"} & set(w["found"]) and "Airpods" in a["found"]


def test_strip_replaces_text_and_keeps_collected_title():
    ex = _ex()
    h = _compat(R.scan(ex), "애플워치 호환 표기")
    R.strip_extra(ex, h)                                       # 자동(사진 안 그림)
    assert ex["title_ko"].startswith("SPORTLINK(SPORTLINK)는 스마트워치 호환 충전 거치대")
    assert ex["title"].startswith("수행 방패(SPORTLINK)는 애플 워치")              # 수집 원문 그대로
    assert ex["keywords"] == ["SPORTLINK", "애플", "워치", "스마트워치", "Airpods", "거치대"]   # 바꾸고 겹친 건 하나로
    assert "images_ko" in ex and not ex["images_ko"][0].get("risk_exclude")       # 자동은 사진 손 안 댐


def test_decide_keeps_to_and_enforce_replaces_new_draft():
    ex = _ex()
    h = _compat(R.scan(ex), "에어팟 호환 표기")
    ex2 = json.loads(json.dumps(ex))
    ex2["images_ko"] = []                                      # 사진 없음 — 글자만
    r = R.decide(ex2, h["key"], "strip", by="u1")
    assert r["ok"] and ex2["risk_decisions"][h["key"]]["to"] == "무선 이어폰"
    pd = {"detail_auto": {"text": "에어팟 호환 이어폰 거치대 — Airpods Pro도 꽂혀요"}}
    R.enforce(pd, ex2)
    assert pd["detail_auto"]["text"] == "무선 이어폰 호환 이어폰 거치대 — 무선 이어폰 Pro도 꽂혀요"


def test_person_strip_retexts_photo_boxes(monkeypatch):
    from src.services import image_edit as IE
    sent = {}
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    monkeypatch.setattr(IE, "plan", lambda ex, kind, idx, fetch=True: {"boxes": [
        {"id": "b1", "src": "适用苹果手表充电支架", "tgt": "스포츠링크 삼합일 애플 워치 충전 거치대"},
        {"id": "b2", "src": "一放秒充", "tgt": "놓으면 초속 충전"}]})

    def apply(ex, kind, idx, ops, by="user", small=None):
        sent["ops"] = ops
        return {"ok": True, "version": "edit:3"}
    monkeypatch.setattr(IE, "apply", apply)
    ex = _ex()
    h = _compat(R.scan(ex), "애플워치 호환 표기")
    R.strip_extra(ex, h, erase_pixels=True)
    assert sent["ops"] == [{"id": "b1", "action": "text", "text": "스포츠링크 삼합일 스마트워치 충전 거치대"}]   # 그 상자만 · 원문 안 봄
    e = ex["images_ko"][0]
    assert e["risk_erase"]["how"] == "retext" and e["risk_erase"]["edit"] == 3 and not e.get("risk_exclude")
    monkeypatch.setattr(IE, "current_key", lambda e: "edit:3")
    assert not [x for x in R.scan(ex)["hits"] if x["key"] == "compat:애플워치 호환 표기" and x.get("images")]   # 다시 안 셈


def test_retext_without_editor_excludes_with_reason(monkeypatch):
    from src.services import image_edit as IE
    monkeypatch.setattr(IE, "configured", lambda: (False, "키 없음"))
    ex = _ex()
    R.strip_extra(ex, _compat(R.scan(ex), "애플워치 호환 표기"), erase_pixels=True)
    assert "사진째 뺌(지금은 사진 편집을 쓸 수 없음)" in ex["images_ko"][0]["risk_exclude"]


def test_decided_compat_is_reapplied_when_it_comes_back(monkeypatch):
    """오너 「AI 초안에 애플 재발 검사」 — 결정 뒤 새 글(초안·번역)에 그 이름이 다시 나오면 같은 결정을 다시 건다."""
    monkeypatch.setattr(R, "learned", lambda: {})
    ex = {"title_ko": "스마트워치 호환 충전 거치대", "keywords": [], "images_ko": [],
          "risk_decisions": {"compat:애플워치 호환 표기": {"action": "strip", "names": ["애플워치"], "to": "스마트워치"}},
          "description_ko": "애플워치를 올려 두면 바로 충전돼요"}
    done = R.auto_apply(ex)
    assert done and ex["description_ko"] == "스마트워치를 올려 두면 바로 충전돼요"


def test_head_note_is_first_line_and_does_not_block_ai_draft():
    from src.seller_console import upload_dispatcher as UD
    note = "※ 충전기·케이블 미포함 — 스탠드만 포함"
    pd = {"detail_head_note": note, "description": "", "detail_auto": {"text": "3in1 스마트워치 호환 충전 거치대예요.", "provider": "anthropic"}}
    cp = UD.head_note(pd, "coupang:gogane")
    assert cp["description"] == note
    filled = UD.fill_empty_description(cp)                     # 고정 줄만 있는 설명 = 빈 설명 → 초안이 실린다
    assert filled["description"].startswith(note) and "3in1 스마트워치" in filled["description"]
    assert UD.head_note(pd, "smartstore:chezgoga") is pd       # 네이버는 설명 칸에 안 넣는다(본문 조립이 맨 위에)
    from src.uploaders import naver_detail as ND
    html = ND.build({**pd, "images": ["https://x/1.jpg"]})
    assert html.index(note) < html.index("https://x/1.jpg")    # 사진보다 먼저 · 맨 위


def test_owner_decision_fields_and_discard(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    from src.seller_console import collect_history_store as store
    box = {"title_ko": _TITLE, "keywords": ["애플"]}
    item = {"id": "a3a35e92", "extra_json": json.dumps(box, ensure_ascii=False)}
    monkeypatch.setattr(D, "_item", lambda iid: (item, "u1"))
    saved = {}
    monkeypatch.setattr(store, "update", lambda iid, seller_ids=None, extra_json="": saved.update(json.loads(extra_json)) or True)
    monkeypatch.setattr(O, "_prevalidate", lambda iid, markets: {"ok": True, "queued": markets})
    out = O._owner_decision("a3a35e92", {}, [], "", ["coupang:gogane"], fields={
        "title_ko": "SPORTLINK 3in1 스마트워치 호환 충전 거치대 무선 이어폰 수납 스탠드",
        "keywords": ["SPORTLINK", "스마트워치", " "], "detail_head_note": "※ 충전기·케이블 미포함 — 스탠드만 포함", "title": "무시"})
    assert out["ok"] and saved["title_ko"].startswith("SPORTLINK 3in1") and saved["keywords"] == ["SPORTLINK", "스마트워치"]
    assert "title" not in saved and saved["owner_fields_log"][0]["before"]["title_ko"] == _TITLE    # 원문 칸은 못 바꾼다 · 앞 값 기록
    fresh = {}
    monkeypatch.setattr(store, "merge_extra", lambda iid, fn, seller_ids=None: fn(fresh))
    r = O._discard("50a13703", "오너 결정 — 국내 상품 등록 안 함")
    assert r["ok"] and fresh["discarded"]["by"] == "owner-oneshot"
    assert not O._discard("50a13703", "")["ok"]                  # 두 번 버리지 않는다


def _ocr_shape_plan(ex, kind, idx, fetch=True):
    """운영(10-21 01:50 SPORTLINK 사진 1) 상자 모양 — 번역본 그림을 OCR로 읽은 상자: 한국어가 `src`, `tgt`는 빈칸."""
    return {"boxes": [{"id": "t0", "src": "스포츠링크", "tgt": ""},
                      {"id": "t3", "src": "애플 워치 충전 거치대", "tgt": ""},
                      {"id": "t8", "src": "주의사항: 판매 상품은 스탠드만 포함되며", "tgt": ""}]}


def test_retext_reads_src_when_box_came_from_ocr_of_translated_image(monkeypatch):
    from src.services import image_edit as IE
    sent = {}
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    monkeypatch.setattr(IE, "plan", _ocr_shape_plan)

    def apply(ex, kind, idx, ops, by="user", small=None):
        sent["ops"] = ops
        return {"ok": True, "version": "edit:1"}
    monkeypatch.setattr(IE, "apply", apply)
    ex = _ex()
    R.strip_extra(ex, _compat(R.scan(ex), "애플워치 호환 표기"), erase_pixels=True)
    assert sent["ops"] == [{"id": "t3", "action": "text", "text": "스마트워치 충전 거치대"}]
    e = ex["images_ko"][0]
    assert e["risk_erase"]["how"] == "retext" and e["risk_erase"]["erased"] == ["애플 워치 충전 거치대"]
    assert not e.get("risk_exclude")


def test_heal_retries_photos_dropped_for_missing_box(monkeypatch):
    """운영에서 이미 「사진째 뺌(번역 글자 상자를 못 찾음)」이 된 4장 — 사전검증 때 같은 결정으로 다시 고친다. 다른 사유는 그대로."""
    from src.services import image_edit as IE
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    monkeypatch.setattr(IE, "plan", _ocr_shape_plan)
    monkeypatch.setattr(IE, "apply", lambda ex, kind, idx, ops, by="user", small=None: {"ok": True, "version": "edit:2"})
    miss = "위험 — 호환 표기(AppleWatch, applewatch) — 사진째 뺌(그 낱말이 든 번역 글자 상자를 못 찾음)"
    ex = _ex()
    ex["images_ko"] = [dict(ex["images_ko"][0], risk_exclude=miss),
                       {"idx": 1, "status": "done", "target_text": "판촉 문구", "risk_exclude": "판촉 — 사진째 뺌(판촉)"}]
    ex["risk_decisions"] = {"compat:애플워치 호환 표기": {"action": "strip", "names": ["애플워치", "애플 워치"], "to": "스마트워치"}}
    assert R.heal_retext_excludes(ex) == ["사진 1"]
    assert not ex["images_ko"][0].get("risk_exclude") and ex["images_ko"][0]["risk_erase"]["edit"] == 2
    assert ex["images_ko"][1]["risk_exclude"] == "판촉 — 사진째 뺌(판촉)"            # 다른 사유는 손 안 댐
    assert R.heal_retext_excludes(ex) == []                                       # 두 번째는 할 일 없음
    # 결정이 없으면 풀지 않는다
    ex2 = _ex()
    ex2["images_ko"][0]["risk_exclude"] = miss
    assert R.heal_retext_excludes(ex2) == [] and ex2["images_ko"][0]["risk_exclude"] == miss
