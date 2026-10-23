"""Y11X(오너 2026-10-17) — 대기함 소화: ⑨ 원문 유지 표기(Proprietary 20) · 한 장짜리 일회성 작업 · OCR 결과 잰 시각 · 보낸 사진 주소 목록."""
import json

import pytest


# ── 1. Y11W-3: 영문 낱말+숫자 모델 표기는 음차하지 않는다 ─────────────────────────────────────────────────────────

def test_proprietary_20_stays_original_through_polish():
    """VRSUK 상세 13번: 텐센트 「프로피리티어 20」 · 다듬기 「프로프라이어터리 20」 → 「Proprietary 20」."""
    from src.services import image_polish as P
    boxes = [{"id": "t0", "src": "Proprietary 20", "tgt": "프로피리티어 20"}]
    cache = {("Proprietary 20", "프로피리티어 20"): {"ai": "프로프라이어터리 20", "pv": P.PROMPT_VER, "tries": 1}}
    r = P.polish_boxes(boxes, {"rule": {}}, cache=cache)["rows"][0]
    assert r["ko"] == "Proprietary 20" and r["why"] == "원문 유지 표기(Proprietary 20)"
    assert P.apply_glossary("Proprietary 20", "프로피리티어 20") == "Proprietary 20"      # AI가 없어도(용어집 단계)
    assert "Proprietary 20" in P._SYSTEM                                                 # ⑨ 규칙 예시에 합침


def test_keep_original_is_narrow():
    from src.services import image_polish as P
    assert P.keep_original("Proprietary 20") == "Proprietary 20"
    assert P.keep_original("EHILÀ™") == "EHILÀ™"
    for s in ("Size 20", "TOP1", "65cm", "reddot award", "AUTOPULENTE", "italia", "正品 20", "1"):
        assert P.keep_original(s) == "", s


def test_redo_flags_transliterated_keep_box_only_when_restorable():
    from src.services import image_edit as IE
    from src.services import image_polish as P
    boxes = [{"src": "Proprietary 20", "tgt": "프로피리티어 20", "h": 267}]
    ed = {"by": P.POLISH_BY, "render": "local", "render_v": IE.RENDER_V,
          "ops": [{"id": "t0", "action": "text", "text": "프로프라이어터리 20"}]}
    assert P._redo_polish(ed, boxes, [1440, 1828])
    assert not P._redo_polish(ed, boxes, None)                                    # 틀이 다르면(되살릴 수 없으면) 그대로
    assert not P._redo_polish(dict(ed, ops=[{"id": "t0", "action": "restore"}]), boxes, [1440, 1828])


# ── 2. Y11W-4: 한 장만 OCR 다시 판정 · 결과줄에 잰 시각 ────────────────────────────────────────────────────────────

def test_ocr_line_ends_with_run_time_kst():
    from src.services import ocr_compare_diag as D
    res = {"at": "2026-10-14T13:02:30+00:00", "pages": [{"verdict": "unknown", "why": "이미지를 내려받지 못했습니다(ValueError)"}],
           "count": {"han": 0, "send": 0, "none": 0, "unknown": 1}}
    # Y12-A: 한 문장 · 끝 = 잰 시각(KST, 표기 없이) · 판정 못 함은 0이 아니면 줄에 남는다(사유는 접힘 `detail`)
    assert D.line(res) == "OCR 판정 완료 · 1장 · 다시 번역할 장 0 · 판정 못 함 1 · 10-14 22:02"
    assert "ValueError" in D.detail(res) and D.detail(res).endswith("10-14 22:02 KST")
    assert D.line({"running": True, "at": "2026-10-14T13:02:30+00:00"}) == "OCR 판정 중… (1~2분)"


@pytest.fixture
def qstate(monkeypatch):
    from src.db import image_translate_queue_pg as st
    box = {}
    monkeypatch.setattr(st, "_enabled", lambda: False)          # 순찰 57: 원자 쓰기(state_update)도 같은 저장소
    monkeypatch.setattr(st, "_MEM_STATE", box)
    return box


def test_oneshot_runs_each_row_once(qstate, monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    from src.services import image_polish as IP
    monkeypatch.setattr(D, "_item", lambda i: ({"id": "it-full"}, "u1"))
    calls = []
    monkeypatch.setattr(IP, "polish_job", lambda i, u, k, x: calls.append(("polish", i, u, k, x)) or {"ok": True, "changed": 1})
    monkeypatch.setattr(D, "run", lambda i, idx: calls.append(("ocr", i, idx)) or {
        "at": "2026-10-17T03:00:00+00:00", "pages": [{"no": 1, "idx": 0, "verdict": "han"}], "count": {"han": 1}})
    qstate[O.QUEUE_KEY] = {"rows": [{"op": "polish_page", "item_id": "it", "kind": "detail", "idx": 12},
                                    {"op": "ocr_recheck", "item_id": "it", "detail_idx": [0]},
                                    {"op": "delete_all", "item_id": "it"}]}
    out = O.drain()
    assert calls == [("polish", "it-full", "u1", "detail", 12), ("ocr", "it-full", [0])]
    assert qstate[O.QUEUE_KEY] == {"rows": []} and O.drain()["picked"] == 0          # 한 번만
    assert out["rows"][2]["result"]["why"].startswith("모르는 작업")
    assert qstate[D.item_key("it-full")]["count"] == {"han": 1}                        # 드로어 줄이 이 결과를 읽는다


# ── 3. Y11W-2: 보낸 사진 주소 목록(해시+URL) — 쿠팡·네이버 같은 꼴 ───────────────────────────────────────────────────

D14 = "https://res.cloudinary.com/x/image/upload/v1/proxy-commerce/edit/yqxlsgzovogceupyhonm.jpg"


def test_sent_images_shape_coupang_and_naver():
    from src.services import sent_images as S
    body = {"items": [{"images": [{"imageType": "REPRESENTATION", "vendorPath": "https://res.cloudinary.com/x/sku1.jpg"},
                                  {"imageType": "DETAIL", "cdnPath": "vendor_inventory/a/d.jpg"}],
                       "contents": [{"contentDetails": [{"detailType": "IMAGE", "content": D14},
                                                        {"detailType": "TEXT", "content": '<p>글</p><img src="https://a/b.jpg">'}]}]},
                      {"images": [{"imageType": "REPRESENTATION", "vendorPath": "https://res.cloudinary.com/x/sku1.jpg"}]}]}
    c = S.from_coupang(body)
    assert [(r["k"], r["url"]) for r in c["images"]] == [("sku", "https://res.cloudinary.com/x/sku1.jpg"),
                                                        ("sku_other", "vendor_inventory/a/d.jpg"),
                                                        ("detail", D14), ("detail", "https://a/b.jpg")]
    assert c["n"] == 4 and len(c["hash"]) == 16 and S.has(c, D14)
    n = S.from_html(f'<div><img src="{D14}" style="x"/><img src=\'https://a/b.jpg\'></div>')
    assert set(n) == set(c) and n["n"] == 2 and S.has(n, D14)


def test_coupang_refresh_records_sent_image_urls(monkeypatch):
    from src.services import coupang_detail_refresh as R
    contents = [{"contentDetails": [{"detailType": "IMAGE", "content": D14}]}]
    monkeypatch.setattr(R, "target", lambda item, up, sid="": {"ready": True, "contents": contents, "hash": "h1", "sku_images": {},
                                                               "translated": 0, "failed": 0, "why": "", "detail_images": 1,
                                                               "providers": {}})
    monkeypatch.setattr(R, "_queue_drop", lambda *a: None)

    class Up:
        def get_product(self, sid):
            return {"statusName": "승인완료", "items": [{"externalVendorSku": "s1", "salePrice": 100, "images": []}]}

        def modify_product(self, body):
            return {"success": True, "market_status": 200, "body": '{"code":"SUCCESS"}'}
    saved = {}
    item = {"id": "it", "extra_json": json.dumps({"uploaded": [{"market": "coupang:gogane", "product_id": "1"}]})}
    rows = R.refresh_item(item, make_up=lambda acc: Up(), save=lambda ex: saved.update(ex))
    assert rows[0]["ok"] and rows[0]["sent_images"]["n"] == 1
    rec = saved["coupang_detail_sync"]["coupang:gogane"]["sent_images"]
    assert rec["images"][0] == {"k": "detail", "h": rec["images"][0]["h"], "url": D14}


def test_coupang_register_summary_carries_sent_images():
    from src.uploaders.coupang_uploader import CoupangUploader
    s = CoupangUploader.sent_summary({"items": [{"contents": [{"contentDetails": [{"detailType": "IMAGE", "content": D14}]}]}]})
    assert s["sent_images"]["images"][0]["url"] == D14


# ── 3-b. 같은 틱의 쿠팡·네이버 저장이 서로 덮지 않는다(10-17 05:10 VRSUK) ─────────────────────────────────────────────

def test_coupang_and_naver_savers_do_not_overwrite_each_other(monkeypatch):
    from src.seller_console import collect_history_store as store
    from src.services import coupang_detail_refresh as R
    from src.services import naver_detail_refresh as N
    base = {"uploaded": [{"market": "coupang:gogane", "product_id": "1"},
                         {"market": "smartstore:chezgoga", "product_id": "2"}],
            "coupang_detail_sync": {"coupang:gogane": {"hash": "old-1650"}}}
    db = {"extra_json": json.dumps(base)}
    monkeypatch.setattr(store, "get", lambda item_id, seller_id=None, seller_ids=None: dict(db, id=item_id))
    monkeypatch.setattr(store, "update", lambda item_id, seller_id=None, seller_ids=None, **f: db.update(f) or True)
    stale_cp, stale_nv = json.loads(db["extra_json"]), json.loads(db["extra_json"])   # 두 잡이 같은 때 읽은 값
    stale_cp["coupang_detail_sync"]["coupang:gogane"] = {"hash": "new-0510", "sent_images": {"n": 33}}
    R.store_save("it", {"u"})(stale_cp)                                               # 쿠팡이 먼저 쓰고
    stale_nv["uploaded"][1]["detail_sync"] = {"hash": "nv-0510", "ok": True}
    N.store_save("it", {"u"})(stale_nv)                                               # 네이버가 처음 읽은 값으로 나중에 쓴다
    got = json.loads(db["extra_json"])
    assert got["coupang_detail_sync"]["coupang:gogane"] == {"hash": "new-0510", "sent_images": {"n": 33}}   # 예전: old-1650
    assert got["uploaded"][1]["detail_sync"] == {"hash": "nv-0510", "ok": True}
