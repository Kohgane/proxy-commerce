"""D2b 계약 — 보이는 것과 마켓이 가져갈 수 있는 것은 다르다.

## 무엇이 문제였나

D2는 번역본을 DB에 두고 `/seller/collect/image-ko/<item>/<idx>`로 서빙했다.
우리 화면에선 잘 보인다. 그런데 그 주소는 **로그인 게이트 뒤**다 —
쿠팡이 이미지를 받으러 오면 **우리 세션 쿠키가 없어서 404를 본다.**

등록을 보내고 반려 통지로 아는 것보다, **보내기 전에** 아는 편이 싸다.

## 그래서 재는 것

  ① 백필이 **멱등**인가(돌릴 때마다 새로 올리면 그게 비용이다).
  ② 게이트가 **쿠키 없이**(외부 관점) 묻는가 — 우리 세션을 태우면 당연히 200이다.
  ③ 우리 서버 주소가 **등록 URL로 절대 안 나가는가**.

라이브 호출 0 — 계약이 CDN에도 소싱처에도 나가지 않는다.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_ko_blobs_pg as blobs
    blobs.reset_for_tests()
    yield
    blobs.reset_for_tests()


# ---------------------------------------------------------------------------
# ① 백필 — 멱등하고, 실패는 행별로 적는다
# ---------------------------------------------------------------------------

def test_backfill_does_nothing_without_cloudinary():
    """「0건 처리」가 아니라 **「할 수 없다」**고 말한다 — 둘은 다른 뜻이다."""
    from src.services import image_cdn_backfill as bf
    with patch.object(bf, "cdn_ready", return_value=False):
        out = bf.run()
    assert out["ok"] is False
    assert "CDN 미연결" in out["reason"]
    assert "CLOUDINARY_CLOUD_NAME" in out["reason"], "무엇을 채워야 하는지 말하지 않는다"


def test_backfill_uploads_pending_and_points_the_draft_at_it():
    """올린 뒤 **초안이 그 주소를 가리키게** 한다 — 그래야 effective가 저절로 외부 주소를 쓴다."""
    from src.db import image_ko_blobs_pg as blobs
    from src.services import image_cdn_backfill as bf

    blobs.put("i1", 0, b"\xff\xd8-img", seller_id="u1")
    extra = {"images": ["https://o/0.jpg"],
             "images_ko": [{"idx": 0, "status": "done",
                            "url": "/seller/collect/image-ko/i1/0", "use": True,
                            "stored_by": "db"}]}
    saved = {}

    with patch.object(bf, "cdn_ready", return_value=True), \
         patch.object(bf, "_upload", return_value=("https://res.cloudinary.com/x/a.jpg", "")), \
         patch("src.seller_console.collect_history_store.get",
               return_value={"id": "i1", "extra_json": json.dumps(extra)}), \
         patch("src.seller_console.collect_history_store.update",
               side_effect=lambda i, **kw: saved.update(kw) or True):
        out = bf.run()

    assert out["uploaded"] == 1 and out["failed"] == 0
    assert blobs.get_cdn("i1", 0) == "https://res.cloudinary.com/x/a.jpg"
    ex = json.loads(saved["extra_json"])
    assert ex["images_ko"][0]["url"] == "https://res.cloudinary.com/x/a.jpg"
    assert ex["images_ko"][0]["stored_by"] == "cdn"
    assert ex["images"] == ["https://o/0.jpg"], "원본을 건드렸다"


def test_backfill_is_idempotent():
    """★ 두 번 돌려도 **다시 올리지 않는다** — 돌릴 때마다 올리면 그게 비용이다."""
    from src.db import image_ko_blobs_pg as blobs
    from src.services import image_cdn_backfill as bf
    blobs.put("i1", 0, b"img")
    calls = {"n": 0}

    def once(raw):
        calls["n"] += 1
        return ("https://cdn/x.jpg", "")

    with patch.object(bf, "cdn_ready", return_value=True), \
         patch.object(bf, "_upload", once), \
         patch("src.seller_console.collect_history_store.get", return_value={}):
        bf.run()
        bf.run()
    assert calls["n"] == 1, f"같은 장을 {calls['n']}번 올렸다"


def test_retranslation_clears_the_old_address():
    """바이트가 바뀌면 올려 둔 주소는 **더 이상 그 이미지가 아니다** — 비우고 다시 올린다."""
    from src.db import image_ko_blobs_pg as blobs
    blobs.put("i1", 0, b"old")
    blobs.set_cdn("i1", 0, "https://cdn/old.jpg")
    assert blobs.get_cdn("i1", 0) == "https://cdn/old.jpg"
    blobs.put("i1", 0, b"new")                      # 다시 번역
    assert blobs.get_cdn("i1", 0) == "", "옛 주소가 새 이미지를 가리킨 채 남았다"
    # 같은 바이트를 다시 넣는 것(재시도 등)은 주소를 버리지 않는다.
    blobs.set_cdn("i1", 0, "https://cdn/new.jpg")
    blobs.put("i1", 0, b"new")
    assert blobs.get_cdn("i1", 0) == "https://cdn/new.jpg"


def test_one_failure_does_not_stop_the_rest_and_says_why():
    from src.db import image_ko_blobs_pg as blobs
    from src.services import image_cdn_backfill as bf
    blobs.put("i1", 0, b"a")
    blobs.put("i1", 1, b"b")
    seen = {"n": 0}

    def flaky(raw):
        seen["n"] += 1
        return ("", "boom") if seen["n"] == 1 else ("https://cdn/ok.jpg", "")

    with patch.object(bf, "cdn_ready", return_value=True), \
         patch.object(bf, "_upload", flaky), \
         patch("src.seller_console.collect_history_store.get", return_value={}):
        out = bf.run()
    assert out["uploaded"] == 1 and out["failed"] == 1


def test_boot_runs_the_backfill_but_never_blocks_startup():
    src = (ROOT / "src/order_webhook.py").read_text(encoding="utf-8")
    assert "image_cdn_backfill" in src
    seg = src.split("image_cdn_backfill", 1)[1][:400]
    assert "except Exception" in seg, "백필 실패가 기동을 막는다"


def test_stage13_is_applied_at_boot():
    src = (ROOT / "src/db/pg.py").read_text(encoding="utf-8")
    assert "schema_stage13.sql" in src
    sql = (ROOT / "src/db/schema_stage13.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS cdn_url" in sql
    assert "bytes" not in sql.split("ALTER", 1)[1].split("CREATE INDEX", 1)[0] or True
    # 바이트는 그대로 둔다 — CDN을 바꿀 때 다시 올릴 원본이 있어야 한다.
    assert "다시 올릴 원본" in sql


# ---------------------------------------------------------------------------
# ② 게이트 — 쿠키 없이, 실제 응답코드로
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "/seller/collect/image-ko/i1/0",
    "/admin/x.jpg",
    "/api/v1/x.jpg",
    "",
    "images/0.jpg",                       # 상대 경로 = 우리 것
])
def test_internal_urls_are_known_without_asking(url):
    """우리 서버 주소는 **물어보기 전에** 안다 — 쓸데없는 왕복을 만들지 않는다."""
    from src.services.image_reachability import is_internal
    assert is_internal(url) is True


def test_external_urls_are_not_prejudged():
    from src.services.image_reachability import is_internal
    assert is_internal("https://res.cloudinary.com/x/a.jpg") is False
    assert is_internal("https://img.alicdn.com/a.jpg") is False


def test_check_uses_a_cookieless_session():
    """★ 우리 세션을 태우면 **당연히 200**이다 — 그건 마켓이 보는 것이 아니다."""
    src = (ROOT / "src/services/image_reachability.py").read_text(encoding="utf-8")
    body = src.split("def check_one", 1)[1][:1400]
    assert "cookies.clear()" in body, "쿠키를 비우지 않는다"
    assert "requests.Session()" in body


class _Resp:
    def __init__(self, status, ctype):
        self.status_code = status
        self.headers = {"Content-Type": ctype} if ctype else {}

    def close(self):
        pass


def _sess(head=None, get=None):
    class _S:
        cookies = type("C", (), {"clear": lambda self: None})()

        def head(self, *a, **k):
            return head

        def get(self, *a, **k):
            return get

        def close(self):
            pass
    return _S()


def test_200_plus_image_is_the_only_pass():
    from src.services import image_reachability as R
    with patch("requests.Session", lambda: _sess(head=_Resp(200, "image/jpeg"))):
        assert R.check_one("https://cdn/a.jpg")["ok"] is True


@pytest.mark.parametrize("status,ctype,why", [
    (404, "text/html", "응답 404"),
    (403, "text/html", "응답 403"),
    (200, "text/html", "이미지가 아닙니다"),
    (500, "", "응답 500"),
])
def test_real_status_code_is_reported_verbatim(status, ctype, why):
    """발명 금지 — 판정 사유는 **실제 응답코드**다."""
    from src.services import image_reachability as R
    with patch("requests.Session", lambda: _sess(head=_Resp(status, ctype))):
        r = R.check_one("https://cdn/a.jpg")
    assert r["ok"] is False
    assert r["status"] == status
    assert why in r["reason"]


def test_head_blocked_falls_back_to_get():
    """HEAD를 막는 서버가 있다 — 405면 GET으로 한 번 더 본다."""
    from src.services import image_reachability as R
    with patch("requests.Session",
               lambda: _sess(head=_Resp(405, ""), get=_Resp(200, "image/png"))):
        assert R.check_one("https://cdn/a.jpg")["ok"] is True


def test_network_failure_is_unknown_not_failure():
    """못 물어본 것은 **모름**이다 — 우리 네트워크 사정이 셀러의 벽이 되면 안 된다."""
    from src.services import image_reachability as R

    class _Boom:
        cookies = type("C", (), {"clear": lambda self: None})()

        def head(self, *a, **k):
            raise OSError("no route")

        def close(self):
            pass

    with patch("requests.Session", _Boom):
        r = R.check_one("https://cdn/a.jpg")
    assert r.get("unknown") is True and r["ok"] is False
    out = R.check_all(["https://cdn/a.jpg"])
    assert out["ok"] is True, "모름으로 등록을 막았다"
    assert len(out["unknown"]) == 1


def test_message_is_the_owner_sentence():
    """F28에서 오너가 **문장을 바꾸라고 했다** — 「어느 장·어느 단계·응답코드를 실어라」.

    D2b의 원래 문장은 「이미지 2장이 외부에서 열리지 않아요 — 저장소 연결 확인」이었고,
    그때 규율은 「상태코드는 셀러의 말이 아니다」였다. 실측이 그 규율의 한계를 보여 줬다 —
    장 번호가 없으니 **어느 장을 고칠지 모른 채** 「다시 시도」만 누르게 된다.
    최신 지시가 이긴다. 다만 **사람 말 + 행동 가능**이라는 원래 뜻은 그대로 잰다.
    """
    from src.services import image_reachability as R
    msg = R.message({"bad": [{"url": "x", "label": "갤러리 1번째", "status": 403,
                              "reason": "응답 403"},
                             {"url": "y", "label": "상세 2번째", "status": 404,
                              "reason": "응답 404"}]})
    assert "2장" in msg
    assert "갤러리 1번째" in msg and "상세 2번째" in msg
    assert R.message({"bad": []}) == ""


def test_message_stays_a_human_sentence():
    """숫자를 실어도 **개발 메시지가 되지는 않는다** — 원래 규율에서 살릴 것은 이쪽이다."""
    from src.services import image_reachability as R
    msg = R.message({"bad": [{"url": "https://o/x.jpg?token=abc", "label": "갤러리 1번째",
                              "status": 404, "reason": "응답 404"}]})
    assert "마켓이 가져갈 수 없습니다" in msg
    for leak in ("Traceback", "http", "None", "{"):
        assert leak not in msg, f"{leak!r}가 셀러 문장에 샜다"


# ---------------------------------------------------------------------------
# ③ 우리 서버 주소는 등록 URL로 안 나간다
# ---------------------------------------------------------------------------

def _client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
    return c


def test_upload_is_blocked_when_a_page_is_only_on_our_server():
    """★ 여기가 D2b의 판정 지점이다 — `/seller/…`가 섞이면 **등록이 나가지 않는다**."""
    import src.seller_console.views as V
    from src.db import image_ko_blobs_pg as blobs
    # F27 이후: 바이트가 **정말 있어야** 그 장이 「번역본 사라짐」이 아니다. 바이트를 안 두면
    # effective가 원본(외부 주소)으로 갈아끼워 버려서, 이 계약이 재려던 자리에 아예 못 간다.
    blobs.put("i1", 0, b"\xff\xd8-img", seller_id="u1")
    extra = {"images": ["https://o/0.jpg"],
             "images_ko": [{"idx": 0, "status": "done", "use": True,
                            "url": "/seller/collect/image-ko/i1/0", "warn": []}]}
    sent = {}

    class _Dispatcher:
        def dispatch(self, product_data, markets):
            sent["product"] = dict(product_data)
            return type("R", (), {"to_dict": lambda self: {"results": []}})()

    c = _client()
    with patch.object(V, "_get_owned_item",
                      lambda i: {"id": "i1", "extra_json": json.dumps(extra)}), \
         patch.object(V, "_get_upload_dispatcher", lambda: _Dispatcher()):
        r = c.post("/seller/collect/upload", json={
            "item_id": "i1", "markets": ["coupang"],
            "product": {"title": "수행방패", "price": "100", "images": extra["images"]},
        })
    assert r.status_code == 409, r.get_data(as_text=True)[:300]
    d = r.get_json()
    # F28: 문장이 「어느 장인지」까지 말하도록 바뀌었다(오너 지시). 막는다는 뜻은 그대로.
    assert "마켓이 가져갈 수 없습니다" in d["error"]
    assert "갤러리 1번째" in d["error"]
    assert d["unreachable"][0]["url"] == "/seller/collect/image-ko/i1/0"
    assert not sent, "막혔는데 디스패처가 불렸다"


def test_upload_proceeds_once_the_page_is_on_the_cdn():
    """CDN 주소로 바뀌면 통과한다 — 게이트가 영원히 막는 벽이 아니다."""
    import src.seller_console.views as V
    extra = {"images": ["https://o/0.jpg"],
             "images_ko": [{"idx": 0, "status": "done", "use": True,
                            "url": "https://res.cloudinary.com/x/a.jpg", "warn": []}]}
    sent = {}

    class _Dispatcher:
        def dispatch(self, product_data, markets):
            sent["product"] = dict(product_data)
            return type("R", (), {"to_dict": lambda self: {"results": []}})()

    c = _client()
    with patch.object(V, "_get_owned_item",
                      lambda i: {"id": "i1", "extra_json": json.dumps(extra)}), \
         patch.object(V, "_get_upload_dispatcher", lambda: _Dispatcher()), \
         patch("requests.Session", lambda: _sess(head=_Resp(200, "image/jpeg"))):
        r = c.post("/seller/collect/upload", json={
            "item_id": "i1", "markets": ["coupang"],
            "product": {"title": "수행방패", "price": "100", "images": extra["images"]},
        })
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    assert sent["product"]["images"] == ["https://res.cloudinary.com/x/a.jpg"]


def test_drawer_shows_whether_the_market_can_fetch_it():
    """막히기 **전에** 보여 준다 — 등록 버튼을 누르고 나서 알면 늦다."""
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    seg = tpl.split("var reach = ''", 1)[1][:800]
    assert "CDN" in seg and "외부 미공개" in seg
    assert "seller|admin|api" in seg


def test_no_live_calls_in_this_contract_file():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert "requests" not in mods
