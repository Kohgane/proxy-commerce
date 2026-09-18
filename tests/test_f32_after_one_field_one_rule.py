"""F32 후속 계약 — 한 필드에 두 규칙을 두지 않는다.

## 실측 (오너 2026-09-18)

Cloudinary 백필이 **5/5 성공**했고 HEAD가 **200 · image/jpeg**를 냈다. 막던 것은 env **값**이었다
— 콘솔의 **Key Name**(`cloudciuga`)을 `CLOUDINARY_CLOUD_NAME`에 넣은 것.

그 과정에서 남은 흠: **저장된 백필 사유에 그 값이 원문 그대로** 화면에 남았다.

## 왜 안 가려졌나 — 같은 「사유」인데 규칙이 둘이었다

| 필드 | 쓰기 | 출력 |
|---|---|---|
| `_LAST_ERROR.detail` | 세척 | 세척된 값 그대로 |
| `cdn_error` | **원문 저장** | **원문 출력** ← 여기가 샜다 |

그리고 길이 규칙(24자 이상)으로는 `cloudciuga`(10자)를 못 잡는다 — **길이로는 안 된다.**

> ★ **한 필드에 두 규칙을 두지 않는다.** 화면에 닿는 사유는 **전부 같은 문**을 지난다.
> 그리고 아는 값은 **이름으로 안다** — 길이로 추측하지 않는다.

**값은 비교에만 쓴다.** 어디에도 적지 않는다.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
JPG = b"\xff\xd8\xff\xe0-bytes"
# 오너 실측 값 그대로 — 이게 화면에 남았다.
CLOUD = "cloudciuga"


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_ko_blobs_pg as blobs
    blobs.reset_for_tests()
    yield
    blobs.reset_for_tests()


@pytest.fixture
def cloud_env(monkeypatch):
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", CLOUD)
    monkeypatch.setenv("CLOUDINARY_API_KEY", "484512345678901")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "sEcReT-VaLuE-1234567890")
    return monkeypatch


# ---------------------------------------------------------------------------
# ① 세척기 — 아는 값은 이름으로 안다
# ---------------------------------------------------------------------------

def test_a_short_config_value_is_masked_by_name_not_by_length(cloud_env):
    """★ **이 판의 판정 지점** — `cloudciuga`(10자)는 길이 규칙에 안 걸린다."""
    from src.utils.redact import scrub_infra
    out = scrub_infra(f"Invalid cloud_name {CLOUD} — must be a valid cloud name")
    assert CLOUD not in out
    assert "[값]" in out
    assert "Invalid cloud_name" in out, "사유까지 지우면 쓸모가 없다"


def test_every_known_credential_value_is_masked(cloud_env):
    from src.utils.redact import scrub_infra
    out = scrub_infra("key=484512345678901 secret=sEcReT-VaLuE-1234567890 cloud=" + CLOUD)
    for leak in (CLOUD, "484512345678901", "sEcReT-VaLuE-1234567890"):
        assert leak not in out, leak


def test_a_short_value_is_not_masked(monkeypatch):
    """네 글자 미만은 안 가린다 — 흔한 낱말을 먹으면 사유를 못 읽는다."""
    from src.utils.redact import scrub_infra
    monkeypatch.setenv("CLOUDINARY_FOLDER", "ab")
    assert "ab" in scrub_infra("upload failed for folder ab")


def test_the_coordinates_are_still_removed(cloud_env):
    """앞서 쓰던 규칙이 살아 있는지 — 이번 추가가 덮어쓰지 않았다."""
    from src.utils.redact import scrub_infra
    out = scrub_infra('connection to server at "db.x.supabase.co" (1.2.3.4), '
                      'port 6543 failed: timeout expired')
    for leak in ("supabase.co", "1.2.3.4", "6543"):
        assert leak not in out
    assert "timeout expired" in out


def test_the_scrubber_never_writes_the_values_anywhere(cloud_env):
    """값은 **비교에만** 쓴다 — 반환값에도, 예외에도 남지 않는다."""
    from src.utils.redact import scrub_infra
    assert CLOUD not in scrub_infra("아무 상관 없는 문장")
    assert scrub_infra("") == ""


# ---------------------------------------------------------------------------
# ② 저장된 사유도 같은 문을 지난다
# ---------------------------------------------------------------------------

def test_a_stored_backfill_reason_is_masked_on_the_way_out(cloud_env):
    """★★ **오너가 본 그 자리** — 저장은 원문이어도 **출력은 세척**된다."""
    from src.db import image_ko_blobs_pg as blobs
    blobs.put("i1", 0, JPG, seller_id="u1")
    blobs.set_cdn("i1", 0, "", error=f"RuntimeError: Invalid cloud_name {CLOUD}")
    st = blobs.status_for_item("i1") or {}
    err = (st.get(("gallery", 0)) or {}).get("cdn_error", "")
    assert CLOUD not in err, err
    assert "Invalid cloud_name" in err, "사유가 사라졌다"


def test_the_backfill_result_rows_are_masked_too(cloud_env):
    """「지금 올리기」가 돌려주는 장별 사유도 같은 문을 지난다."""
    from src.db import image_ko_blobs_pg as blobs
    from src.services import image_cdn_backfill as bf
    blobs.put("i1", 0, JPG, seller_id="u1")
    with patch("src.media.image_pipeline.upload_bytes",
               return_value={"ok": False, "secure_url": "", "public_id": "", "bytes": 0,
                             "error": f"RuntimeError: Invalid cloud_name {CLOUD}", "keys": []}):
        out = bf.run()
    assert out["failed"] == 1
    assert CLOUD not in out["results"][0]["error"]
    assert "Invalid cloud_name" in out["results"][0]["error"]


def test_the_last_write_error_stays_masked(cloud_env):
    """앞서 세척되던 쪽이 그대로인지 — 두 규칙을 하나로 모으며 한쪽을 잃지 않았다."""
    from src.db import image_ko_blobs_pg as blobs
    blobs._note_error("put", f"OperationalError: cloud {CLOUD} refused")
    assert CLOUD not in blobs.last_error()["detail"]


def test_no_reason_reaching_the_screen_carries_a_known_value(cloud_env):
    """★ 화면에 닿는 사유 **전부**를 훑는다 — 한 자리라도 새면 규칙이 둘인 것이다."""
    from src.db import image_ko_blobs_pg as blobs
    from src.services import image_cdn_backfill as bf
    blobs.put("i1", 0, JPG, seller_id="u1")
    blobs.set_cdn("i1", 0, "", error=f"boom {CLOUD}")
    blobs._note_error("put", f"boom {CLOUD}")
    with patch("src.media.image_pipeline.upload_bytes",
               return_value={"ok": False, "secure_url": "", "public_id": "", "bytes": 0,
                             "error": f"boom {CLOUD}", "keys": []}):
        run = bf.run()
    reasons = [
        (blobs.status_for_item("i1") or {}).get(("gallery", 0), {}).get("cdn_error", ""),
        blobs.last_error().get("detail", ""),
        blobs.probe().get("reason", ""),
        *[r.get("error", "") for r in run.get("results") or []],
    ]
    for r in reasons:
        assert CLOUD not in r, r


def test_the_diag_screen_shows_the_masked_reason(cloud_env):
    """끝에서 한 번 더 — 화면 HTML에 값이 없다."""
    import src.seller_console.views as V
    from src.db import image_ko_blobs_pg as blobs
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    blobs.put("i1", 0, JPG, seller_id="u1")
    blobs.set_cdn("i1", 0, "", error=f"RuntimeError: Invalid cloud_name {CLOUD}")
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
        s["user_role"] = "admin"
    with patch.object(V, "_seller_identities", lambda: {"u1"}):
        html = c.get("/seller/admin/image-storage").get_data(as_text=True)
    assert CLOUD not in html, "화면에 값이 그대로 남았다"
