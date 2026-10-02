"""R3(오너 2026-10-01) — 캡처 파일 중복 자리 합치기.

실측: 오너가 올린 `static/help/iphone/` 9장 중 **c1~c4가 같은 파일**(md5 동일, 420,875B). 같은 사진 넷이 화면 C에
줄줄이 뜨면 「동작마다 다른 화면」으로 읽힌다 → 내용 해시가 같으면 **첫 자리만** 띄우고 나머지는 「C1과 같은 사진」.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def shots_dir(tmp_path, monkeypatch):
    import src.seller_console.views as V
    (tmp_path / "a1.png").write_bytes(b"A1")
    (tmp_path / "a2.png").write_bytes(b"A2")
    for k in ("c1", "c2", "c3", "c4"):
        (tmp_path / f"{k}.png").write_bytes(b"SAME")
    (tmp_path / "b2.png").write_bytes(b"B")               # B 화면 안의 중복(b2=b3)
    (tmp_path / "b3.png").write_bytes(b"B")
    monkeypatch.setattr(V, "_IPHONE_SHOTS_DIR", str(tmp_path))
    return tmp_path


def test_helper_keeps_first_and_marks_duplicates(shots_dir):
    import src.seller_console.views as V
    s = V._iphone_shots(("c1", "c2", "c3", "c4", "c5"))
    assert s["c1"].endswith("/c1.png") and "c2" not in s and "c5" not in s
    assert s["_dups"] == {"c2": "c1", "c3": "c1", "c4": "c1"}


def test_make_screen_shows_one_image_and_says_so(shots_dir):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/seller/guide/iphone/make").get_data(as_text=True)
    assert h.count('src="/seller/static/help/iphone/c1.png"') == 1 and "/c2.png" not in h
    for k in ("c2", "c3", "c4"):
        assert f'data-role="shot-dup-{k}"' in h and "C1와 같은 사진" in h
    assert "C2 = C1(같은 파일)" in h and "C5 비어 있음" in h


def test_use_screen_dedupes_within_itself(shots_dir):
    from src.order_webhook import app
    h = app.test_client().get("/seller/guide/iphone/use").get_data(as_text=True)
    assert 'src="/seller/static/help/iphone/b2.png"' in h and "/b3.png" not in h
    assert 'data-role="shot-dup-b3"' in h and "위 사진과 같은 화면이에요." in h
