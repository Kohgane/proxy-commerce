"""순찰 123b — 일회성 작업 `naver_split_ok`: 화면 「가격대별로 나눠 등록」 확인과 같은 입구(`collect_naver_split_ok`)를 그 상품 계정으로."""
from __future__ import annotations

from flask import jsonify


def test_naver_split_ok_op_routes_to_view(monkeypatch):
    from src.services import ocr_compare_diag as D
    from src.services import oneshot_ops as O
    from src.seller_console import views as V
    assert "naver_split_ok" in O.OPS
    monkeypatch.setattr(D, "_item", lambda iid: ({"id": "it-1"}, "u-1"))
    seen = {}

    def fake(iid):
        from flask import request, session
        seen["iid"], seen["uid"], seen["body"] = iid, session.get("user_id"), request.get_json(silent=True)
        return jsonify({"ok": True, "split": {"groups": [{"suffix": "(액세서리)", "skus": ["a", "b"], "min": 1, "max": 2}]}}), 200
    monkeypatch.setattr(V, "collect_naver_split_ok", fake)
    out = O._run({"op": "naver_split_ok", "item_id": "it-1"})
    assert out["ok"] and seen == {"iid": "it-1", "uid": "u-1", "body": {}}
    assert out["groups"] == [{"suffix": "(액세서리)", "min": 1, "max": 2, "n": 2}]
    out = O._run({"op": "naver_split_ok", "item_id": "it-1", "cancel": True})
    assert seen["body"] == {"cancel": True}


def test_naver_split_ok_op_reports_409(monkeypatch):
    from src.services import ocr_compare_diag as D
    from src.services import oneshot_ops as O
    from src.seller_console import views as V
    monkeypatch.setattr(D, "_item", lambda iid: ({"id": "it-1"}, "u-1"))
    monkeypatch.setattr(V, "collect_naver_split_ok", lambda iid: (jsonify({"ok": False, "error": "지금 계산으로는 나눌 필요가 없어요"}), 409))
    out = O._run({"op": "naver_split_ok", "item_id": "it-1"})
    assert out["ok"] is False and out["status"] == 409 and "나눌 필요" in out["why"]
