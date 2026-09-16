"""F31 계약 — 반환 타입이 좁으면 사유가 죽는다.

## 실측 (오너 2026-09-16, 진단 화면)

저장된 장 **5**(96~126KB) · Cloudinary env **3개 있음** · DB **연결됨** ·
외부 주소 **「아직 없음」** · 백필 사유 **「업로드가 주소를 돌려주지 않았습니다」 ×5**.

## 원인 — `Optional[str]`

`_upload_to_cdn`(`src/media/image_pipeline.py`)의 반환이 `str | None`이었다.
그 한 칸에 **여섯 가지 실패**가 전부 `None`으로 접혔다:

  ① 토글 꺼짐(`IMAGE_CDN_UPLOAD_ENABLED=0`) ② 자격 미설정 ③ `ADAPTER_DRY_RUN=1`
  ④ cloudinary 미설치(`logger.debug` 한 줄) ⑤ SDK 예외(`logger.warning`)
  ⑥ 응답은 왔는데 `secure_url`/`url`이 없음

호출부는 「주소가 없다」만 알았고, **왜인지는 로그 안에서 끝났다.**

> **「됐다/안 됐다」만 담는 타입은 안 된 이유를 담을 칸이 없다.**
> 그 이유는 어디에도 안 남는다.

→ `upload_bytes()`가 **dict**를 돌려준다: `ok · secure_url · public_id · bytes ·
  error · keys`. `keys`는 **다음 판의 답**이다 — 우리가 아는 키가 없으면 무슨 키가
  왔는지를 실어야 이름을 고칠 수 있다(발명 금지).

**라이브 호출 0** — cloudinary SDK를 목으로 세운다(업로드가 한 번도 나가지 않는다).
"""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
JPG = b"\xff\xd8\xff\xe0-korean"


@pytest.fixture
def cdn_env(monkeypatch):
    """자격이 **있는** 상태(오너 실측과 같음) — 여기서부터가 진짜 갈림길이다."""
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "demo")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "key")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "secret")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
    import src.media.image_pipeline as P
    monkeypatch.setattr(P, "_CDN_UPLOAD_ENABLED", True, raising=False)
    return monkeypatch


def _fake_sdk(monkeypatch, *, result=None, raises=None):
    """cloudinary SDK를 세운다 — **네트워크로 나가지 않는다.**"""
    up = types.ModuleType("cloudinary.uploader")

    def _upload(_fileobj, **_opts):
        if raises is not None:
            raise raises
        return result

    up.upload = _upload
    root = types.ModuleType("cloudinary")
    root.config = lambda **kw: None
    root.uploader = up
    monkeypatch.setitem(sys.modules, "cloudinary", root)
    monkeypatch.setitem(sys.modules, "cloudinary.uploader", up)


# ---------------------------------------------------------------------------
# ① 업로드 결과 — dict로, 사유까지
# ---------------------------------------------------------------------------

def test_secure_url_comes_back_as_a_dict(cdn_env):
    from src.media.image_pipeline import upload_bytes
    _fake_sdk(cdn_env, result={"secure_url": "https://res.cloudinary.com/demo/a.jpg",
                               "public_id": "folder/a", "bytes": 12345})
    out = upload_bytes(JPG)
    assert out["ok"] is True
    assert out["secure_url"] == "https://res.cloudinary.com/demo/a.jpg"
    assert out["public_id"] == "folder/a"
    assert out["bytes"] == 12345
    assert out["error"] == ""


def test_a_response_without_a_url_names_the_keys_it_did_have(cdn_env):
    """★★ **F31의 판정 지점** — 「주소를 안 돌려줬다」에 **응답 키 목록**을 싣는다.

    다음엔 키 이름이 답이다. 무엇이 왔는지를 그대로 실어야 이름을 고칠 수 있다.
    """
    from src.media.image_pipeline import upload_bytes
    _fake_sdk(cdn_env, result={"asset_id": "x", "signature": "y", "resource_type": "image"})
    out = upload_bytes(JPG)
    assert out["ok"] is False
    assert "응답 키 목록" in out["error"]
    for key in ("asset_id", "resource_type", "signature"):
        assert key in out["error"], out["error"]
    assert out["keys"] == ["asset_id", "resource_type", "signature"]


def test_the_sdk_exception_text_survives(cdn_env):
    """SDK가 뭐라고 했는지 **그대로** — 「Invalid api_key」가 여기 있어야 다음 수리가 된다."""
    from src.media.image_pipeline import upload_bytes
    _fake_sdk(cdn_env, raises=RuntimeError("Invalid api_key abc"))
    out = upload_bytes(JPG)
    assert out["ok"] is False
    assert "RuntimeError" in out["error"]
    assert "Invalid api_key" in out["error"]


def test_each_blocked_branch_says_its_own_reason(cdn_env):
    """★ 여섯 갈래가 **각각 다른 문장**이다 — 전부 「주소 없음」이던 것이 이 병이었다."""
    import src.media.image_pipeline as P
    from src.media.image_pipeline import upload_bytes
    _fake_sdk(cdn_env, result={"secure_url": "https://x/y.jpg"})

    cdn_env.setattr(P, "_CDN_UPLOAD_ENABLED", False, raising=False)
    assert "IMAGE_CDN_UPLOAD_ENABLED=0" in upload_bytes(JPG)["error"]
    cdn_env.setattr(P, "_CDN_UPLOAD_ENABLED", True, raising=False)

    cdn_env.delenv("CLOUDINARY_API_KEY", raising=False)
    err = upload_bytes(JPG)["error"]
    assert "자격 미설정" in err and "CLOUDINARY_API_KEY" in err
    cdn_env.setenv("CLOUDINARY_API_KEY", "key")

    cdn_env.setenv("ADAPTER_DRY_RUN", "1")
    assert "ADAPTER_DRY_RUN=1" in upload_bytes(JPG)["error"]
    cdn_env.setenv("ADAPTER_DRY_RUN", "0")

    assert "바이트가 없습니다" in upload_bytes(b"")["error"]


def test_a_missing_sdk_is_no_longer_silent(cdn_env):
    """예전엔 `logger.debug` 한 줄이라 **아무 데도 안 보였다**."""
    from src.media.image_pipeline import upload_bytes
    real = __import__("builtins").__import__

    def _no_cloudinary(name, *a, **k):
        if name.startswith("cloudinary"):
            raise ImportError("No module named 'cloudinary'")
        return real(name, *a, **k)

    cdn_env.setitem(sys.modules, "cloudinary", None)
    with patch("builtins.__import__", _no_cloudinary):
        out = upload_bytes(JPG)
    assert out["ok"] is False
    assert "cloudinary 라이브러리 없음" in out["error"]


def test_the_error_never_carries_keys_or_hosts(cdn_env):
    """사유는 남기고 **좌표·긴 토큰은 지운다** — 진단 화면도 접속 지도가 되면 안 된다."""
    from src.media.image_pipeline import upload_bytes
    _fake_sdk(cdn_env, raises=RuntimeError(
        "upload failed for https://api.cloudinary.com/v1_1/demo/image/upload "
        "with api_key=123456789012345678901234567890"))
    err = upload_bytes(JPG)["error"]
    assert "https://" not in err
    assert "123456789012345678901234567890" not in err
    assert "upload failed" in err, "사유까지 지우면 쓸모가 없다"


def test_the_old_wrapper_is_a_thin_shell():
    """`_upload_to_cdn`은 껍데기다 — 업로드를 두 벌로 두지 않는다."""
    src = (ROOT / "src/media/image_pipeline.py").read_text(encoding="utf-8")
    fn = re.search(r"def _upload_to_cdn\(.*?\n(?=\ndef |\n# ---)", src, re.S)
    assert fn
    body = "\n".join(l for l in fn.group(0).splitlines()
                     if not l.strip().startswith("#"))
    assert "upload_bytes(" in body
    assert "cloudinary.uploader.upload" not in body, "업로드가 두 곳에 있다"


# ---------------------------------------------------------------------------
# ② 백필 — 사유를 그대로 올리고, 원본 되돌림은 실패다
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_ko_blobs_pg as blobs
    blobs.reset_for_tests()
    yield
    blobs.reset_for_tests()


def test_backfill_fills_cdn_url_when_upload_succeeds(cdn_env):
    """★ mock이 `secure_url`을 주면 `cdn_url`이 채워진다."""
    from src.db import image_ko_blobs_pg as blobs
    from src.services import image_cdn_backfill as bf
    blobs.put("i1", 0, JPG, seller_id="u1")
    with patch("src.media.image_pipeline.upload_bytes",
               return_value={"ok": True, "secure_url": "https://res.cloudinary.com/x/a.jpg",
                             "public_id": "p", "bytes": 9, "error": "", "keys": []}):
        out = bf.run()
    assert out["ok"] is True and out["uploaded"] == 1 and out["failed"] == 0
    assert blobs.get_cdn("i1", 0) == "https://res.cloudinary.com/x/a.jpg"


def test_backfill_stores_the_reason_when_upload_errors(cdn_env):
    """★ mock이 `error`를 주면 그 사유가 **그대로** 저장된다."""
    from src.db import image_ko_blobs_pg as blobs
    from src.services import image_cdn_backfill as bf
    blobs.put("i1", 0, JPG, seller_id="u1")
    with patch("src.media.image_pipeline.upload_bytes",
               return_value={"ok": False, "secure_url": "", "public_id": "", "bytes": 0,
                             "error": "RuntimeError: Invalid api_key", "keys": []}):
        out = bf.run()
    assert out["failed"] == 1 and out["uploaded"] == 0
    assert blobs.get_cdn("i1", 0) == ""
    st = blobs.status_for_item("i1") or {}
    assert "Invalid api_key" in (st.get(("gallery", 0)) or {}).get("cdn_error", "")


def test_giving_back_the_original_url_counts_as_failure(cdn_env):
    """★ **「성공 같은 실패」** — `ok`가 아니면 주소가 있어도 실패다.

    옛 `process_image`는 업로드가 안 되면 `processed_url = image_url`(원본)로 돌려줬다.
    그런 반환을 성공으로 읽으면, 등록에 **소싱처 원본 주소**가 그대로 나간다.
    """
    from src.db import image_ko_blobs_pg as blobs
    from src.services import image_cdn_backfill as bf
    blobs.put("i1", 0, JPG, seller_id="u1")
    with patch("src.media.image_pipeline.upload_bytes",
               return_value={"ok": False, "secure_url": "https://item.taobao.com/원본.jpg",
                             "public_id": "", "bytes": 0,
                             "error": "업로드 응답에 주소가 없습니다", "keys": []}):
        out = bf.run()
    assert out["failed"] == 1
    assert blobs.get_cdn("i1", 0) == "", "원본 주소를 CDN 주소로 적었다"


def test_backfill_reports_each_page(cdn_env):
    """F31-3: 「지금 올리기」가 **장별** 성공/실패/사유를 돌려준다."""
    from src.db import image_ko_blobs_pg as blobs
    from src.services import image_cdn_backfill as bf
    blobs.put("i1", 0, JPG, seller_id="u1")
    blobs.put("i1", 1, JPG, seller_id="u1")
    calls = {"n": 0}

    def _alternate(raw, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": True, "secure_url": "https://res.cloudinary.com/x/1.jpg",
                    "public_id": "", "bytes": 1, "error": "", "keys": []}
        return {"ok": False, "secure_url": "", "public_id": "", "bytes": 0,
                "error": "RuntimeError: quota exceeded", "keys": []}

    with patch("src.media.image_pipeline.upload_bytes", side_effect=_alternate):
        out = bf.run()
    results = out["results"]
    assert len(results) == 2
    assert [r["ok"] for r in results] == [True, False]
    assert "quota exceeded" in results[1]["error"]
    assert results[1]["idx"] == 1


def test_the_screen_unfolds_the_per_page_results():
    tpl = (ROOT / "src/seller_console/templates/image_storage_diag.html").read_text(encoding="utf-8")
    body = "\n".join(l for l in tpl.splitlines() if not l.strip().startswith("//"))
    assert "d.results" in body
    assert "r.error" in body
    assert "location.reload" in body and "!d.failed" in body, \
        "실패가 있는데 새로고침하면 사유를 읽기 전에 사라진다"


# ---------------------------------------------------------------------------
# ③ 번역 시점 업로드도 같은 함수
# ---------------------------------------------------------------------------

def test_translate_time_upload_uses_the_same_function():
    """업로드 경로가 두 벌이면 한쪽만 고치게 된다(F22 큐 소비자 포함)."""
    src = (ROOT / "src/services/image_translate_store.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "upload_bytes" in body
    assert "_upload_to_cdn" not in body, "옛 좁은 반환을 아직 쓴다"


def test_translate_time_failure_keeps_its_reason(cdn_env):
    """CDN이 안 되면 DB로 가되, **왜 안 됐는지**는 들고 간다."""
    from src.services.image_translate_store import store_translated
    with patch("src.media.image_pipeline.upload_bytes",
               return_value={"ok": False, "secure_url": "", "public_id": "", "bytes": 0,
                             "error": "RuntimeError: Invalid api_key", "keys": []}):
        out = store_translated("i1", 0, "aGVsbG8=", seller_id="u1")
    assert out["stored_by"] == "db"
    assert "Invalid api_key" in out.get("cdn_error", "")


def test_scrubber_lives_in_one_place():
    """세척기가 셋이 될 뻔했다 — 합쳤는지 잰다(한쪽만 고치면 나머지가 샌다)."""
    from src.utils.redact import scrub_infra
    assert "supabase.co" not in scrub_infra('at "db.x.supabase.co" port 6543')
    for path in ("src/seller_console/views.py", "src/db/image_ko_blobs_pg.py"):
        body = (ROOT / path).read_text(encoding="utf-8")
        assert "from src.utils.redact import scrub_infra" in body, path
